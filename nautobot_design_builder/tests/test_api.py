import unittest

from nautobot.utilities.testing import APIViewTestCases

from nautobot_design_builder.models import Design, DesignInstance, Journal, JournalEntry
from nautobot_design_builder.tests.util import create_test_view_data


class DesignTest(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = Design
    brief_fields = ["display", "id", "name", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()


class DesignInstanceTest(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = DesignInstance
    brief_fields = ["display", "id", "name", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()


class JournalTest(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = Journal
    brief_fields = ["display", "id", "url"]

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()


class JournalEntryTest(
    APIViewTestCases.GetObjectViewTestCase,
    APIViewTestCases.ListObjectsViewTestCase,
    APIViewTestCases.NotesURLViewTestCase,
):
    model = JournalEntry
    brief_fields = None

    @classmethod
    def setUpTestData(cls):
        create_test_view_data()

    @unittest.skip
    def test_list_objects_brief(self):
        """Brief is not supported for journal entries."""
        pass