"""Base Design Job class definition."""

import sys
import traceback
from abc import ABC, abstractmethod
from os import path
from typing import Dict
import yaml

from django.core.files.base import ContentFile
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from jinja2 import TemplateError

from nautobot.extras.models import Status
from nautobot.apps.jobs import Job, DryRunVar, StringVar, BooleanVar
from nautobot.extras.models import FileProxy
from nautobot.extras.jobs import JobForm

from nautobot_design_builder.errors import DesignImplementationError, DesignModelError
from nautobot_design_builder.jinja2 import new_template_environment
from nautobot_design_builder.design import Environment
from nautobot_design_builder.context import Context
from nautobot_design_builder import models
from nautobot_design_builder import choices


class DesignJob(Job, ABC):  # pylint: disable=too-many-instance-attributes
    """The base Design Job class that all specific Design Builder jobs inherit from.

    DesignJob is an abstract base class that all design implementations must implement.
    Any design that is to be included in the list of Jobs in Nautobot *must* include
    a Meta class.
    """

    dryrun = DryRunVar()

    @classmethod
    @abstractmethod
    def Meta(cls) -> Job.Meta:  # pylint: disable=invalid-name
        """Design jobs must provide either a Meta class method or a Meta class."""

    def __init__(self, *args, **kwargs):
        """Initialize the design job."""
        # rendered designs
        self.environment: Environment = None
        self.designs = {}
        self.rendered_design = None
        self.rendered = None

        super().__init__(*args, **kwargs)

    @classmethod
    def design_mode(cls):
        """Determine the implementation mode for the design."""
        return getattr(cls.Meta, "design_mode", choices.DesignModeChoices.CLASSIC)

    @classmethod
    def is_deployment_job(cls):
        """Determine if a design job has been set to deployment mode."""
        return cls.design_mode() == choices.DesignModeChoices.DEPLOYMENT

    @classmethod
    def deployment_name_field(cls):
        """Determine what the deployment name field is.

        Returns `None` if no deployment has been set in the job Meta class. In this
        case the field will default to `deployment_name`
        """
        getattr(cls.Meta, "deployment_name_field", None)

    @classmethod
    def determine_deployment_name(cls, data):
        """Determine the deployment name field, if specified."""
        if not cls.is_deployment_job():
            return None
        deployment_name_field = cls.deployment_name_field()
        if deployment_name_field is None:
            if "deployment_name" not in data:
                raise DesignImplementationError("No name was provided for the deployment.")
            return data["deployment_name"]
        return data[deployment_name_field]

    @classmethod
    def _get_vars(cls):
        """Retrieve the script variables for the job.

        If no deployment name field has been specified this method will
        also add a `deployment_name` field.
        """
        cls_vars = {}
        if cls.is_deployment_job():
            if cls.deployment_name_field() is None:
                cls_vars["deployment_name"] = StringVar(
                    label="Deployment Name",
                    max_length=models.DESIGN_NAME_MAX_LENGTH,
                )
            cls_vars["import_mode"] = BooleanVar(label="Import Mode", default=False)

        cls_vars.update(super()._get_vars())
        return cls_vars

    @classmethod
    def as_form_class(cls):
        """Dynamically generate the job form.

        This will add the deployment name field, if needed, and also provides
        a clean method that call's the context validations methods.
        """
        fields = {name: var.as_field() for name, var in cls._get_vars().items()}
        old_clean = JobForm.clean
        context_class = cls.Meta.context_class  # pylint:disable=no-member

        def clean(self):
            cleaned_data = old_clean(self)
            if self.is_valid():
                context = context_class(cleaned_data)
                context.validate()
            return cleaned_data

        fields["clean"] = clean
        return type("DesignJobForm", (JobForm,), fields)

    def design_model(self):
        """Get the related Job."""
        return models.Design.objects.for_design_job(self.job_result.job_model)

    def post_implementation(self, context: Context, environment: Environment):
        """Similar to Nautobot job's `post_run` method, but will be called after a design is implemented.

        Any design job that requires additional work to be completed after the design
        has been implemented can provide a `post_implementation` method. This method will be
        called after the entire set of design files has been implemented and the database
        transaction has been committed.

        Args:
            context (Context): The render context that was used for rendering the design files.
            environment (Environment): The build environment that consumed the rendered design files. This is useful for accessing the design journal.
        """

    def _merge_top_level_lists(self, data1: dict, data2: dict) -> dict:
        """Merge top-level lists from two YAML data structures.

        Pass an empty dict as data1 to merge any duplicate top-level lists present in data2.

        Args:
            data1 (dict): First YAML data structure
            data2 (dict): Second YAML data structure to merge into data1

        Returns:
            dict: Merged YAML data structure
        """
        merged = data1.copy()
        for key, value in data2.items():
            if key in merged:
                if isinstance(merged[key], list) and isinstance(value, list):
                    merged[key].extend(value)
            else:
                merged[key] = value
        return merged

    def render(self, context: Context, filename: str) -> str:
        """High level function to render the Jinja design templates into YAML.

        Args:
            context (Context object): a tree of variables that can include templates for values
            filename (str): file name of the Jinja design template

        Raises:
            ex: If there are any rendering errors raise a TemplateError but also include the traceback, Jinja file name and line numbers

        Returns:
            str: YAML data structure rendered from input Jinja template
        """
        search_paths = []
        cls = self.__class__
        # We pass a list of directories to the jinja template environment
        # to be used for search paths in the FileSystemLoader. This list
        # of paths is compiled from the directory location of the current
        # design job and its entire inheritance tree. In order to produce
        # this list, we traverse the inheritance tree upwards until we
        # get to the toplevel base class, `DesignJob`
        while cls is not DesignJob:
            class_dir = path.dirname(sys.modules[cls.__module__].__file__)
            search_paths.append(class_dir)
            cls = cls.__bases__[0]

        env = new_template_environment(context, search_paths)

        try:
            rendered = env.get_template(filename).render()
            
            # split the rendered YAML into documents (separated by ---)
            yaml_docs = yaml.safe_load_all(rendered)
            
            # merge top-level lists from each document
            merged = {}
            for doc in yaml_docs:
                if doc:  # skip empty documents
                    merged = self._merge_top_level_lists(merged, doc)

            return yaml.dump(merged)
        except TemplateError as ex:
            info = sys.exc_info()[2]
            summary = traceback.extract_tb(info, -1)[0]
            self.logger.fatal("%s:%d", filename, summary.lineno)
            raise ex

    def render_design(self, context, design_file):
        """Wrapper function to take in rendered YAML from the design and convert to structured data and assign to the design property of a class instance.

        Args:
            context (Context object): a tree of variables that can include templates for values
            design_file (str): Filename of the design file to render.
        """
        self.rendered = self.render(context, design_file)
        design = yaml.safe_load(self.rendered)
        self.designs[design_file] = design

        # no need to save the rendered content if yaml loaded
        # it okay
        self.rendered = None
        return design

    def render_report(self, context: Context, journal: Dict) -> str:
        """Wrapper function to create rendered markdown report from the design job's Jinja report template.

        Args:
            context (Context object): a tree of variables that can include templates for values
            journal (dict): A dictionary containing keys matching to ORM classes containing lists of Nautobot objects that were created by the design job

        Returns:
            str: job report data in markdown format
        """
        return self.render(
            {
                "context": context,
                "journal": journal,
            },
            getattr(self.Meta, "report"),
        )

    def implement_design(self, context, design_file, commit):
        """Render the design_file template using the provided render context."""
        design = self.render_design(context, design_file)
        self.environment.implement_design(design, commit)

    def _setup_changeset(self, deployment_name: str):
        if not self.is_deployment_job():
            return None, None

        try:
            instance = models.Deployment.objects.get(name=deployment_name, design=self.design_model())
            self.logger.info('Existing design instance of "%s" was found, re-running design job.', deployment_name)
            instance.last_implemented = timezone.now()
        except models.Deployment.DoesNotExist:
            self.logger.info('Implementing new design "%s".', deployment_name)
            content_type = ContentType.objects.get_for_model(models.Deployment)
            instance = models.Deployment(
                name=deployment_name,
                design=self.design_model(),
                last_implemented=timezone.now(),
                status=Status.objects.get(content_types=content_type, name=choices.DeploymentStatusChoices.ACTIVE),
                version=self.design_model().version,
            )
        instance.validated_save()
        change_set, created = models.ChangeSet.objects.get_or_create(
            deployment=instance,
            job_result=self.job_result,
        )
        if created:
            change_set.validated_save()

        previous_change_set = instance.change_sets.order_by("-last_updated").exclude(job_result=self.job_result).first()
        return (change_set, previous_change_set)

    def run(self, dryrun: bool = False, **kwargs):  # pylint: disable=arguments-differ
        """Render the design and implement it within a build Environment object."""
        try:
            return self._run_in_transaction(dryrun, **kwargs)
        finally:
            if self.rendered:
                rendered_design = path.basename(self.rendered_design)
                rendered_design, _ = path.splitext(rendered_design)
                if not rendered_design.endswith(".yaml") and not rendered_design.endswith(".yml"):
                    rendered_design = f"{rendered_design}.yaml"
                self.save_design_file(rendered_design, self.rendered)
            for design_file, design in self.designs.items():
                output_file = path.basename(design_file)
                # this should remove the .j2
                output_file, _ = path.splitext(output_file)
                if not output_file.endswith(".yaml") and not output_file.endswith(".yml"):
                    output_file = f"{output_file}.yaml"
                self.save_design_file(output_file, yaml.safe_dump(design))

    @transaction.atomic
    def _run_in_transaction(self, dryrun: bool, **data):  # pylint: disable=too-many-branches
        """Render the design and implement it within a build Environment object.

        This version of `run` is wrapped in a transaction and will roll back database changes
        on error. In general, this method should only be called by the `run` method.
        """
        sid = transaction.savepoint()

        self.logger.info("Building %s", getattr(self.Meta, "name"))
        extensions = getattr(self.Meta, "extensions", [])

        design_files = None

        data["import_mode"] = self.is_deployment_job() and data.get("import_mode", False)
        data["deployment_name"] = self.determine_deployment_name(data)
        change_set, previous_change_set = self._setup_changeset(data["deployment_name"])

        self.job_result.job_kwargs = {"data": self.serialize_data(data)}

        self.logger.info("Building %s", getattr(self.Meta, "name"))
        extensions = getattr(self.Meta, "extensions", [])
        self.environment = Environment(
            logger=self.logger,
            extensions=extensions,
            change_set=change_set,
            import_mode=data["import_mode"],
        )

        if data["import_mode"]:
            self.logger.info("Running in import mode for %s", data["deployment_name"])

        design_files = None

        if hasattr(self.Meta, "context_class"):
            context = self.Meta.context_class(data=data, job_result=self.job_result)
            context.validate()
        else:
            context = {}

        if hasattr(self.Meta, "design_file"):
            design_files = [self.Meta.design_file]
        elif hasattr(self.Meta, "design_files"):
            design_files = self.Meta.design_files
        else:
            self.logger.fatal("No design template specified for design.")
            raise DesignImplementationError("No design template specified for design.")

        try:
            for design_file in design_files:
                self.implement_design(context, design_file, not dryrun)

            if previous_change_set:
                deleted_object_ids = previous_change_set - change_set
                if deleted_object_ids:
                    self.logger.info(
                        "Decommissioning %d objects that are no longer part of this design.", deleted_object_ids.count()
                    )
                    change_set.deployment.decommission(*deleted_object_ids, local_logger=self.logger)

            if not dryrun:
                self.post_implementation(context, self.environment)
                # The ChangeSet stores the design (with Nautobot identifiers from post_implementation)
                # for future operations (e.g., updates)
                if self.is_deployment_job():
                    change_set.deployment.status = Status.objects.get(
                        content_types=ContentType.objects.get_for_model(models.Deployment),
                        name=choices.DeploymentStatusChoices.ACTIVE,
                    )
                    change_set.deployment.save()
                    change_set.save()

                if hasattr(self.Meta, "report"):
                    report = self.render_report(context, self.environment.journal)
                    output_filename: str = path.basename(getattr(self.Meta, "report"))
                    if output_filename.endswith(".j2"):
                        output_filename = output_filename[0:-3]
                    self.logger.info(report)
                    self.save_design_file(output_filename, report)
            else:
                transaction.savepoint_rollback(sid)
                self.logger.info("%s can be imported successfully - No database changes made", self.name)
        except (DesignImplementationError, DesignModelError) as ex:
            transaction.savepoint_rollback(sid)
            self.logger.fatal("Failed to implement design")
            self.logger.fatal(str(ex))
            raise ex
        except Exception as ex:
            transaction.savepoint_rollback(sid)
            raise ex

    def save_design_file(self, filename, content):
        """Save some content to a job file.

        This is only supported on Nautobot 2.0 and greater.

        Args:
            filename (str): The name of the file to save.
            content (str): The content to save to the file.
        """
        FileProxy.objects.create(
            name=filename,
            job_result=self.job_result,
            file=ContentFile(content.encode("utf-8"), name=filename),
        )
