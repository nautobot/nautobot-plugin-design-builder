"""Utilities for setting up tests and test data."""

from nautobot.extras.models import Status
from nautobot.extras.models import JobResult, Job
from nautobot.tenancy.models import Tenant

from nautobot_design_builder.models import Design, Deployment, ChangeSet, ChangeRecord
from nautobot_design_builder.tests.designs import test_designs


def populate_sample_data():
    """Populate the database with some sample data."""
    job = Job.objects.get(name="Initial Data")
    job_result, _ = JobResult.objects.get_or_create(name="Test", job_model=job)

    design, _ = Design.objects.get_or_create(job=job)
    deployment, _ = Deployment.objects.get_or_create(
        design=design,
        name="Initial Data",
        status=Status.objects.get(name="Active"),
        live_state=Status.objects.get(name="Active"),
    )
    ChangeSet.objects.get_or_create(deployment=deployment, job_result=job_result)


def create_test_view_data():
    """Creates test data for view and API view test cases."""
    job_classes = [
        test_designs.SimpleDesign,
        test_designs.SimpleDesign3,
        test_designs.SimpleDesignReport,
        test_designs.IntegrationDesign,
    ]
    for i, job_class in enumerate(job_classes, 1):
        # Core models
        job = Job.objects.get(module_name=job_class.__module__, job_class_name=job_class.__name__)
        job_result = JobResult.objects.create(name=f"Test Result {i}", job_model=job)
        object_created_by_job = Tenant.objects.create(name=f"Tenant {i}")

        # Design Builder models
        instance = Deployment.objects.create(
            design=Design.objects.get(job_id=job.id),
            name=f"Test Instance {i}",
            status=Status.objects.get(name="Active"),
        )
        change_set = ChangeSet.objects.create(deployment=instance, job_result=job_result)
        full_control = i == 1  # Have one record where full control is given, more than one where its not.
        ChangeRecord.objects.create(
            change_set=change_set, design_object=object_created_by_job, full_control=full_control, index=0
        )
