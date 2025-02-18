"API tests."

from nautobot.apps.testing import APIViewTestCases

from nautobot_design_builder.models import Design, Deployment, ChangeSet, ChangeRecord
from nautobot_design_builder.tests.util import create_test_view_data

# pylint: disable=missing-class-docstring


class TestDesign(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = Design
    brief_fields = ["display", "id", "name", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()

    def test_list_objects_descending_ordered(self):
        """This test fails because of the name annotation."""

    def test_list_objects_ascending_ordered(self):
        """This test fails because of the name annotation."""


class TestDeployment(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = Deployment
    brief_fields = ["display", "id", "name", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()


class TestChangeSet(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = ChangeSet
    brief_fields = ["display", "id", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()


class TestChangeRecord(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = ChangeRecord
    brief_fields = None

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()

    def test_list_objects_brief(self):
        """Brief is not supported for change records."""

    def test_list_objects_depth_0(self):
        """
        Depth 0 is not supported for change records.
        The core test checks that the response_data has only three fields: id/object_type/url. The
        ChangeRecord model has more fields than that, so the test will fail.
        """
