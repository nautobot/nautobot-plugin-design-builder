"""Nested serializers for design builder."""
from nautobot.core.api import BaseModelSerializer
from rest_framework.relations import HyperlinkedIdentityField

from nautobot_design_builder.models import Design, DesignInstance, Journal


class NestedDesignSerializer(BaseModelSerializer):
    """Nested serializer for the design model."""

    url = HyperlinkedIdentityField(view_name="plugins-api:nautobot_design_builder-api:design-detail")

    class Meta:
        """Nested serializer options for the design model."""

        model = Design
        fields = ["id", "url", "name"]


class NestedDesignInstanceSerializer(BaseModelSerializer):
    """Nested serializer for the design instance model."""

    url = HyperlinkedIdentityField(view_name="plugins-api:nautobot_design_builder-api:designinstance-detail")

    class Meta:
        """Nested serializer options for the design instance model."""

        model = DesignInstance
        fields = ["id", "url", "name"]


class NestedJournalSerializer(BaseModelSerializer):
    """Nested serializer for the journal model."""

    url = HyperlinkedIdentityField(view_name="plugins-api:nautobot_design_builder-api:journal-detail")

    class Meta:
        """Nested serializer options for the journal model."""

        model = Journal
        fields = ["id", "url"]