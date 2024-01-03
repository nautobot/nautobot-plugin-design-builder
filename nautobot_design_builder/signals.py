"""Signal handlers that fire on various Django model signals."""
from itertools import chain
import logging

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.models import Job, Status
from nautobot.utilities.choices import ColorChoices

from .design_job import DesignJob
from .models import Design, DesignInstance
from . import choices

_LOGGER = logging.getLogger(__name__)


@receiver(nautobot_database_ready, sender=apps.get_app_config("nautobot_design_builder"))
def create_design_instance_statuses(**kwargs):
    """Create a default set of statuses for design instances."""
    content_type = ContentType.objects.get_for_model(DesignInstance)
    color_mapping = {
        "Active": ColorChoices.COLOR_GREEN,
        "Decommissioned": ColorChoices.COLOR_GREY,
        "Disabled": ColorChoices.COLOR_GREY,
        "Deployed": ColorChoices.COLOR_GREEN,
        "Pending": ColorChoices.COLOR_ORANGE,
        "Rolled back": ColorChoices.COLOR_RED,
    }
    for _, status_name in chain(choices.DesignInstanceStatusChoices, choices.DesignInstanceLiveStateChoices):
        status, _ = Status.objects.get_or_create(name=status_name, defaults={"color": color_mapping[status_name]})
        status.content_types.add(content_type)


@receiver(post_save, sender=Job)
def create_design_model(sender, instance: Job, **kwargs):  # pylint:disable=unused-argument
    """Create a `Design` instance for each `DesignJob`.

    This receiver will fire every time a `Job` instance is saved. If the
    `Job` inherits from `DesignJob` then look for a corresponding `Design`
    model in the database and create it if not found.

    Args:
        sender: The Job class
        instance (Job): Job instance that has been created or updated.
    """
    if instance.job_class and issubclass(instance.job_class, DesignJob):
        _, created = Design.objects.get_or_create(job=instance)
        if created:
            _LOGGER.debug("Created design from %s", instance)