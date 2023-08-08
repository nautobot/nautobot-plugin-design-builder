"""Extra action tags that are not part of the core Design Builder."""
from functools import reduce
import operator

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Q

from nautobot.dcim.models import Cable
from nautobot.extras.models import Status
from nautobot.ipam.models import Prefix

import netaddr
from design_builder.design import Builder
from design_builder.design import ModelInstance

from design_builder.errors import DesignImplementationError
from design_builder.ext import Extension
from design_builder.jinja2 import network_offset


class LookupMixin:
    """A helper mixin that provides a way to lookup objects."""

    def lookup_by_content_type(self, app_label, model_name, query):
        """Perform a query on a model.

        Args:
            app_label: Content type app-label that the model exists in.
            model_name_: Name of the model for the query.
            query (_type_): Dictionary to be used for the query.

        Raises:
            DesignImplementationError: If no matching object is found or no
            matching content-type is found.

        Returns:
            Any: The object matching the query.
        """
        try:
            content_type = ContentType.objects.get_by_natural_key(app_label, model_name)
            model_class = content_type.model_class()
            queryset = model_class.objects
        except ContentType.DoesNotExist:
            raise DesignImplementationError(f"Could not find model class for {model_class}")

        return self.lookup(queryset, query)

    def lookup(self, queryset, query):  # pylint: disable=R0201
        """Perform a single object lookup from a queryset.

        Args:
            queryset: Queryset (e.g. Status.objects.all) from which to query.
            query: Query params to filter by.

        Raises:
            DesignImplementationError: If either no object is found, or multiple objects are found.

        Returns:
            Any: The object matching the query.
        """
        # TODO: Convert this to lookup via ModelInstance
        for key, value in query.items():
            if hasattr(value, "instance"):
                query[key] = value.instance
        try:
            return queryset.get(**query)
        except ObjectDoesNotExist:
            raise DesignImplementationError(f"no {queryset.model.__name__} matching {query}")
        except MultipleObjectsReturned:
            raise DesignImplementationError(f"Multiple {queryset.model.__name__} objects match {query}")


class LookupExtension(Extension, LookupMixin):
    """Lookup a model instance and assign it to an attribute."""

    attribute_tag = "lookup"

    def attribute(self, *args, value, model_instance) -> None:  # pylint:disable=arguments-differ
        """Provides the `!lookup` attribute that will lookup an instance.

        This action tag can be used to lookup an object in the database and
        assign it to an attribute of another object.

        Args:
            value: A filter describing the object to get. Keys should map to lookup
            parameters equivalent to Django's `filter()` syntax for the given model.
            The special `type` parameter will override the relationship's model class
            and instead lookup the model class using the `ContentType`. The value
            of the `type` field must match `ContentType` `app_label` and `model` fields.

        Raises:
            DesignImplementationError: if no matching object was found.

        Returns:
            The attribute name and found object.

        Example:
            ```yaml
            cables:
            - "!lookup:termination_a":
                    content-type: "dcim.interface"
                    device__name: "device1"
                    name: "Ethernet1/1"
              "!lookup:termination_b":
                    content-type: "dcim.interface"
                    device__name: "device2"
                    name: "Ethernet1/1"
            ```
        """
        if len(args) < 1:
            raise DesignImplementationError('No attribute given for the "!lookup" tag.')

        attribute = args[0]
        query = {}
        if isinstance(value, str):
            if len(args) < 2:
                raise DesignImplementationError("No query attribute was given")
            query = {args[1]: value}
        elif isinstance(value, dict):
            query = value
        else:
            raise DesignImplementationError("the lookup requires a query attribute and value or a query dictionary.")

        content_type = query.pop("content-type", None)
        if content_type is None:
            descriptor = getattr(model_instance.model_class, attribute)
            model_class = descriptor.field.related_model
            app_label = model_class._meta.app_label
            model_name = model_class._meta.model_name
        else:
            app_label, model_name = content_type.split(".")

        return attribute, self.lookup_by_content_type(app_label, model_name, query)


class CableConnectionExtension(Extension, LookupMixin):
    """Connect a cable termination to another cable termination."""

    attribute_tag = "connect_cable"

    def attribute(self, value, model_instance) -> None:
        """Connect a cable termination to another cable termination.

        Args:
            value: Query for the `termination_b` side. This dictionary must
            include a field `status` or `status__<lookup param>` that is either
            a reference to a status object (former) or a lookup key/value to
            get a status (latter). The query must also include enough
            differentiating lookup params to retrieve a single matching termination
            of the same type as the `termination_a` side.

        Raises:
            DesignImplementationError: If no `status` was provided, or no matching
            termination was found.

        Returns:
            None: This tag does not return a value, as it adds a deferred object
            representing the cable connection.

        Example:
            ```yaml
            devices:
            - name: "Device 2"
              site__name: "Site"
              status__name: "Active"
              device_role__name: "test-role"
              device_type__model: "test-type"
              interfaces:
                - name: "GigabitEthernet1"
                  type: "1000base-t"
                  status__name: "Active"
                  "!connect_cable":
                    status__name: "Planned"
                    device: "!ref:device1"
                    name: "GigabitEthernet1"
            ```
        """
        query = {**value}
        status = query.pop("status", None)
        if status is None:
            for key in list(query.keys()):
                if key.startswith("status__"):
                    status_lookup = key[len("status__") :]  # noqa: E203
                    status = Status.objects.get(**{status_lookup: query.pop(key)})
                    break
        elif isinstance(status, dict):
            status = Status.objects.get(**status)
        elif hasattr(status, "instance"):
            status = status.instance

        if status is None:
            raise DesignImplementationError("No status given for cable connection")

        remote_instance = self.lookup(model_instance.model_class.objects, query)
        model_instance.deferred.append("cable")
        model_instance.deferred_attributes["cable"] = [
            model_instance.__class__(
                self.object_creator,
                model_class=Cable,
                attributes={
                    "status": status,
                    "termination_a": model_instance,
                    "!create_or_update:termination_b_type": ContentType.objects.get_for_model(remote_instance),
                    "!create_or_update:termination_b_id": remote_instance.id,
                },
            )
        ]


class NextPrefixExtension(Extension):
    """Provision the next prefix for a given set of parent prefixes."""

    attribute_tag = "next_prefix"

    def attribute(self, value: dict, model_instance) -> None:
        """Provides the `!next_prefix` attribute that will calculate the next available prefix.

        Args:
            value: A filter describing the parent prefix to provision from. If `prefix`
                is one of the query keys then the network and prefix length will be
                split and used as query arguments for the underlying Prefix object. The
                requested prefix length must be specified using the `length` dictionary
                key. All other keys are passed on to the query filter directly.

        Raises:
            DesignImplementationError: if value is not a dictionary, the prefix is improperly formatted
                or no query arguments were given. This error is also raised if the supplied parent
                prefixes are all full.

        Returns:
            The next available prefix of the requested size represented as a string.

        Example:
            ```yaml
            prefixes:
            - "!next_prefix":
                    prefix:
                    - "10.0.0.0/23"
                    - "10.0.2.0/23"
                    length: 24
                status__name: "Active"
            ```
        """
        if not isinstance(value, dict):
            raise DesignImplementationError("the next_prefix tag requires a dictionary of arguments")

        length = value.pop("length", None)
        if length is None:
            raise DesignImplementationError("the next_prefix tag requires a prefix length")

        if len(value) == 0:
            raise DesignImplementationError("no search criteria specified for prefixes")

        query = Q(**value)
        if "prefix" in value:
            prefixes = value.pop("prefix")
            prefix_q = []
            if isinstance(prefixes, str):
                prefixes = [prefixes]
            elif not isinstance(prefixes, list):
                raise DesignImplementationError("Prefixes should be a string (single prefix) or a list.")

            for prefix_str in prefixes:
                prefix_str = prefix_str.strip()
                prefix = netaddr.IPNetwork(prefix_str)
                prefix_q.append(
                    Q(
                        prefix_length=prefix.prefixlen,
                        network=prefix.network,
                        broadcast=prefix.broadcast,
                    )
                )
            query = Q(**value) & reduce(operator.or_, prefix_q)

        prefixes = Prefix.objects.filter(query)
        return "prefix", self._get_next(prefixes, length)

    def _get_next(self, prefixes, length) -> str:  # pylint:disable=no-self-use
        """Return the next available prefix from a parent prefix.

        Args:
            prefixes (str): Comma separated list of prefixes to search for available subnets.
            length (int): The requested prefix length.

        Returns:
            str: The next available prefix
        """
        length = int(length)
        for requested_prefix in prefixes:
            for available_prefix in requested_prefix.get_available_prefixes().iter_cidrs():
                if available_prefix.prefixlen <= length:
                    return f"{available_prefix.network}/{length}"
        raise DesignImplementationError(f"No available prefixes could be found from {list(map(str, prefixes))}")


class ChildPrefixExtension(Extension):
    """Calculates a child Prefix string in CIDR notation."""

    attribute_tag = "child_prefix"

    def attribute(self, value: dict, model_instance) -> None:
        """Provides the `!child_prefix` attribute.

        !child_prefix calculates a child prefix using a parent prefix
        and an offset. The parent prefix can either be a string CIDR
        style prefix or it can refer to a previously created `Prefix`
        object.

        Args:
            value: a dictionary containing the `parent` prefix (string or
            `Prefix` instance) and the `offset` in the form of a CIDR
            string. The length of the child prefix will match the length
            provided in the offset string.

        Raises:
            DesignImplementationError: if value is not a dictionary, or the
            prefix or offset are improperly formatted

        Returns:
            The computed prefix string.

        Example:
            ```yaml
            prefixes:
            - "!next_prefix":
                    prefix:
                    - "10.0.0.0/23"
                    length: 24
                status__name: "Active"
                "!ref": "parent_prefix"
            - "!child_prefix":
                    parent: "!ref:parent_prefix"
                    offset: "0.0.0.0/25"
                status__name: "Active"
            - "!child_prefix":
                    parent: "!ref:parent_prefix"
                    offset: "0.0.0.128/25"
                status__name: "Active"
            ```
        """
        if not isinstance(value, dict):
            raise DesignImplementationError("the child_prefix tag requires a dictionary of arguments")

        parent = value.pop("parent", None)
        if parent is None:
            raise DesignImplementationError("the child_prefix tag requires a parent")
        if isinstance(parent, ModelInstance):
            parent = str(parent.instance.prefix)
        elif not isinstance(parent, str):
            raise DesignImplementationError("parent prefix must be either a previously created object or a string.")

        offset = value.pop("offset", None)
        if offset is None:
            raise DesignImplementationError("the child_prefix tag requires an offset")
        if not isinstance(offset, str):
            raise DesignImplementationError("offset must be string")

        return "prefix", network_offset(parent, offset)


class BGPPeeringExtension(Extension):
    """Create BGP peerings in the BGP Models Plugin."""

    attribute_tag = "bgp_peering"

    def __init__(self, object_creator: Builder):
        """Initialize the BGPPeeringExtension.

        This initializer will import the necessary BGP models. If the
        BGP models plugin is not installed then it raises a DesignImplementationError.

        Raises:
            DesignImplementationError: Raised when the BGP Models Plugin is not installed.
        """
        super().__init__(object_creator)
        try:
            from nautobot_bgp_models.models import PeerEndpoint, Peering  # pylint:disable=import-outside-toplevel

            self.PeerEndpoint = PeerEndpoint  # pylint:disable=invalid-name
            self.Peering = Peering  # pylint:disable=invalid-name
        except ModuleNotFoundError:
            raise DesignImplementationError(
                "the `bgp_peering` tag can only be used when the bgp models plugin is installed."
            )

    @staticmethod
    def _post_save(sender, instance, **kwargs) -> None:
        print("Post Save Callback. Sender:", id(sender))
        peering_instance: ModelInstance = instance
        endpoint_a = peering_instance.instance.endpoint_a
        endpoint_z = peering_instance.instance.endpoint_z
        endpoint_a.peer, endpoint_z.peer = endpoint_z, endpoint_a
        endpoint_a.save()
        endpoint_z.save()

    def attribute(self, value, model_instance) -> None:
        """This attribute tag creates or updates a BGP peering for two endpoints.

        !bgp_peering will take an `endpoint_a` and `endpoint_z` argument to correctly
        create or update a BGP peering. Both endpoints can be specified using typical
        Design Builder syntax.

        Args:
            value (dict): dictionary containing the keys `entpoint_a`
            and `endpoint_z`. Both of these keys must be dictionaries
            specifying a way to either lookup or create the appropriate
            peer endpoints.

        Raises:
            DesignImplementationError: if the supplied value is not a dictionary
            or it does not include `endpoint_a` and `endpoint_z` as keys.


        Returns:
            dict: Dictionary that can be used by the design.Builder to create
            the peerings.

        Example:
        ```yaml
        bgp_peerings:
        - "!bgp_peering":
              endpoint_a:
                  "!create_or_update:routing_instance__autonomous_system__asn": "64496"
                  "!create_or_update:source_ip":
                      "interface__device__name": "device1"
                      "interface__name": "Ethernet1/1"
              endpoint_z:
                  "!create_or_update:routing_instance__autonomous_system__asn": "64500"
                  "!create_or_update:source_ip":
                      "interface__device__name": "device2"
                      "interface__name": "Ethernet1/1"
          status__name: "Active"
        ```
        """
        if not (isinstance(value, dict) and value.keys() >= {"endpoint_a", "endpoint_z"}):
            raise DesignImplementationError(
                "bgp peerings must be supplied a dictionary with `endpoint_a` and `endpoint_z`."
            )

        # copy the value so it won't be modified in later
        # use
        retval = {**value}
        endpoint_a = ModelInstance(self.object_creator, self.PeerEndpoint, retval.pop("endpoint_a"))
        endpoint_z = ModelInstance(self.object_creator, self.PeerEndpoint, retval.pop("endpoint_z"))
        peering_a = None
        peering_z = None
        try:
            peering_a = endpoint_a.instance.peering
            peering_z = endpoint_z.instance.peering
        except self.Peering.DoesNotExist:
            pass

        # try to prevent empty peerings
        if peering_a == peering_z:
            if peering_a:
                retval["!update:pk"] = peering_a.pk
        else:
            if peering_a:
                peering_a.delete()
            if peering_z:
                peering_z.delete()

        retval["endpoints"] = [endpoint_a, endpoint_z]
        endpoint_a.attributes["peering"] = model_instance
        endpoint_z.attributes["peering"] = model_instance

        model_instance.connect(ModelInstance.POST_SAVE, BGPPeeringExtension._post_save)
        return retval
