"""
Defines tests and mock to test the sphinx pyreverse tool

Created on Oct 8, 2019

@author: doublethefish
"""
try:
    from contextlib import redirect_stdout
    from io import StringIO
except ImportError:
    # It's likely we're in pyton2 instead of python3
    import sys
    import contextlib  # pylint: disable=ungrouped-imports
    from io import BytesIO as StringIO  # pylint: disable=ungrouped-imports

    @contextlib.contextmanager
    def redirect_stdout(target):
        """ Mimics python3's redirect_stdout function """
        oldio = (sys.stdout, sys.stderr)
        sys.stdout = target
        sys.stderr = target
        try:
            yield
        finally:
            sys.stdout, sys.stderr = oldio


import os
import unittest
import shutil
import tempfile

import test.mock_subprocess
import test.mock_pil
from mock import Mock
import sphinx_pyreverse
import sphinx_pyreverse.uml_generate_directive


class TempdirGuard(object):
    """ creates and deletes a tmp-dir compatible with python2 and 3 """

    def __init__(self):
        self.path = tempfile.mkdtemp(prefix="sphinx_pyreverse_test")

    def __enter__(self):
        return self

    def __exit__(self, x_type, x_value, x_traceback):
        shutil.rmtree(self.path)  # always clean up on exit


class TestUMLGenerateDirectiveBase(unittest.TestCase):
    """ A collection of tests for the UMLGenerateDirective object """

    def gen(self):
        """ Constructs and returns a mocked UMLGenerateDirectiver instance """

        class MockEnv(object):  # pylint: disable=missing-docstring
            def __init__(self):  # pylint: disable=missing-docstring
                self.srcdir = "."

        class MockDocSettings(object):  # pylint: disable=missing-docstring
            def __init__(self):  # pylint: disable=missing-docstring
                self.env = MockEnv()

        class MockDoc(object):  # pylint: disable=missing-docstring
            def __init__(self):  # pylint: disable=missing-docstring
                self.settings = MockDocSettings()
                self.current_source = "."

        class MockState(object):  # pylint: disable=missing-docstring
            def __init__(self):  # pylint: disable=missing-docstring
                self.document = MockDoc()

        return sphinx_pyreverse.UMLGenerateDirective(
            name="test",
            arguments=["noexist_module", ":classes:", ":packages:"],
            options=None,
            content=None,
            lineno=None,
            content_offset=None,
            block_text=None,
            state=MockState(),
            state_machine=None,
        )


class TestUMLGenerateDirective(TestUMLGenerateDirectiveBase):
    """ A collection of tests for the UMLGenerateDirective object """

    def test_ctor(self):
        """ simply constructs a UMLGenerateDirectiver instance with mock values """
        instance = self.gen()
        self.assertIsNotNone(instance)

    def test_run(self):
        """ simply invokes run with the default setup parameters """
        instance = self.gen()
        instance.run()

    def test_uml_dir_creation(self):
        """ test that the uml directory is created under the right circumstances

        This just captures current behaviour - there should be no problem changing it.
        """
        try:
            FileNotFoundError  # noqa: F823
        except NameError:
            # In python2 we need to define this built-in, but must ignore it on
            # python3's flake8
            FileNotFoundError = (  # noqa: F823,E501 pylint: disable=redefined-builtin,invalid-name
                OSError
            )
        instance = self.gen()
        with TempdirGuard() as tempdir:
            mock_dir = os.path.join(tempdir.path, "noexist.dir")
            instance.state.document.settings.env.srcdir = mock_dir
            self.assertTrue(os.path.exists(tempdir.path))
            self.assertFalse(os.path.exists(mock_dir))

            # Check that spinhx_pyreverse doesn't create all the directories.
            with self.assertRaises(
                FileNotFoundError, msg="sphinx_pyreverse should not call mdkir -p"
            ):
                instance.run()

            self.assertFalse(os.path.exists(mock_dir))

            # Now make the parent dir, sphinx_pyreverse should create everything below
            # that, to a single depth
            os.mkdir(mock_dir)
            try:
                instance.run()
            except FileNotFoundError:
                raise RuntimeError(
                    "sphinx_pyreverse should have created a single directory"
                )
            self.assertTrue(os.path.exists(mock_dir))

    def test_generate_same_twice(self):
        """ check that there are no side-effects of processing the same module twice """
        instance = self.gen()
        instance.run()
        instance.run()
        # TODO: extend the subprocess mock so we can interegate how many times pyreverse
        # was called (should only be once)

    def test_invalid_flags(self):
        """ test graceful handling & reporting of errors in parameters """
        instance = self.gen()
        instance.arguments = ["module_name", ":bad_arg:"]
        try:
            instance.run()
        except ValueError as exception:
            self.assertTrue("invalid flags encountered" in str(exception))

    def test_valid_flags(self):
        """ ensure we accept the currently know valid-flags for pyreverse """
        instance = self.gen()
        for args in ((":classes:", ":packages:"), (":classes:",), (":packages:",)):
            instance.arguments = ["module_name"] + list(args)
            instance.run()

    def test_generate_img(self):
        """ cause UMLGenerateDirective.run() to call generate_image for all branches """
        instance = self.gen()

        for width_under_test, expected_scale in ((0, 100), (1, 100), (2000, 50)):
            with test.mock_pil.DimsUnderTestGuard(width=width_under_test):
                mock_module = test.mock_pil.PIL_MOCK.Image  # pylint: disable=no-member
                actual_width = mock_module.open("noexist").size[0]
                self.assertEqual(actual_width, width_under_test)
                res = instance.run()
                self.assertEqual(
                    res[0]["scale"], expected_scale, "Failed for %d" % width_under_test
                )

    def test_generate_img_no_pil(self):
        """ ensure we handle not have the PIL library gracefully

        The intent is to resize too-wide files """
        instance = self.gen()
        old_image = sphinx_pyreverse.uml_generate_directive.IMAGE
        sphinx_pyreverse.uml_generate_directive.IMAGE = None
        instance.run()
        sphinx_pyreverse.uml_generate_directive.IMAGE = old_image

    def test_setup(self):
        """ simply calls the setup function, ensuring no errors """
        self.assertEqual(sphinx_pyreverse.setup(Mock()), None)


class TestLogFixture(TestUMLGenerateDirectiveBase):
    """ Test logging related aspects of the plugin by capturing output """

    def test_pyreverse_fails(self):
        """ Test that we get output logging when the pyreverse fails """
        with test.mock_subprocess.FailExecuteGuard():
            checking = test.mock_subprocess._CHECK_OUTPUT_FAILS  # pylint: disable=W0212
            self.assertEqual(checking, True)
            mock_module = test.mock_subprocess.SUBPROCESS_MOCK
            func_mock = mock_module.check_output  # pylint: disable=no-member
            func_mock.side_effect = test.mock_subprocess.CalledProcessError()

            instance = self.gen()

            with StringIO() as buf, redirect_stdout(buf):
                with self.assertRaises(test.mock_subprocess.CalledProcessError):
                    test.mock_subprocess.failing_call("")
                self.assertEqual(buf.getvalue(), "")

            with StringIO() as buf, redirect_stdout(buf):
                with self.assertRaises(test.mock_subprocess.CalledProcessError):
                    instance.run()
                self.assertEqual(buf.getvalue(), "dummy output\n")
