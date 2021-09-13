"""This module provides a set of pytest hooks for generating Adaptavist test run results from test reports."""

import logging
import os
import subprocess
from contextlib import suppress
from ._pytest_adaptavist import PytestAdaptavist
import pytest
from ._atm_configuration import atm_user_is_valid
from ._helpers import assume, import_module
from .metablock import MetaBlock

META_BLOCK_TIMEOUT = 600

@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """Prepare and start logging/reporting (called at the beginning of the test process)."""

    # register custom markers
    config.addinivalue_line("markers", "testcase: mark test method as test case implementation (for internal use only)")
    config.addinivalue_line("markers", "project(project_key): mark test method to be related to given project (used to create appropriate test case key")
    config.addinivalue_line("markers", "block(reason): mark test method to be blocked")

    if config.getoption("-h") or config.getoption("--help"):
        return

    adaptavist = PytestAdaptavist(config)
    config.pluginmanager.register(adaptavist, "adaptavist2")  # something registered as adaptavist before me?!?
    
    # support for pytest-assume >= 1.2.1 (needs to be done after any potential call of pytest_configure)
    if hasattr(pytest, "assume") and not hasattr(pytest, "_failed_assumptions"):
        pytest_assume = import_module("pytest_assume")
        if pytest_assume and hasattr(pytest_assume, "plugin"):
            # pytest-assume 1.2.1 is using _FAILED_ASSUMPTIONS and _ASSUMPTION_LOCALS
            setattr(pytest, "_failed_assumptions", getattr(pytest_assume.plugin, "_FAILED_ASSUMPTIONS", []))
            setattr(pytest, "_assumption_locals", getattr(pytest_assume.plugin, "_ASSUMPTION_LOCALS", []))

    if not hasattr(pytest, "_failed_assumptions"):
        # overwrite all assumption related attributes by local ones
        setattr(pytest, "_failed_assumptions", [])
        setattr(pytest, "_assumption_locals", [])
        pytest.assume = assume

    setattr(pytest, "_showlocals", config.getoption("showlocals"))

    # support for pytest.block
    def block(msg=""):
        __tracebackhide__ = True  # pylint: disable=unused-variable
        raise Blocked(msg=msg)

    block.Exception = Blocked

    pytest.block = block

    # Store metadata for later usage (e.g. adaptavist traceability).
    metadata = getattr(config, "_metadata", os.environ)

    build_usr = "jenkins" # TODO: REVERT THIS!!!!
    build_url = metadata.get("BUILD_URL")
    jenkins_url = metadata.get("JENKINS_URL")
    code_base = metadata.get("GIT_URL", get_code_base_url())
    branch = metadata.get("GIT_BRANCH")
    commit = metadata.get("GIT_COMMIT")

    adaptavist.build_url = "/".join(build_url.split("/")[:5]) if build_url and jenkins_url and build_url.startswith(jenkins_url) else build_url
    adaptavist.code_base = code_base.replace(":", "/").replace(".git", "").replace("git@", "https://") if code_base and code_base.startswith("git@") else code_base

    # only report results to adaptavist if:
    #     - branch is master
    #     - user is jenkins
    #     - env is jenkins
    # note: we might need the possibility to create adaptavist results from a local test run (beit for testing purpose or whatever)

    # if user is jenkins
    #   if branch is master then report using getpass.getuser()
    #   else disable report
    # else
    #   report using getpass.getuser()

    # => automated flag set and executedby = "jenkins" means official test run
    # => automated flag set and executedby != "jenkins" means inofficial test run (not valid with respect to DoD)
    if build_usr == "jenkins" and build_url and jenkins_url and build_url.startswith(jenkins_url):
        if branch != "origin/master":
            # disable reporting
            setattr(config.option, "adaptavist", False)

    if build_usr != "jenkins":
        if not atm_user_is_valid(build_usr):
            # disable reporting
            setattr(config.option, "adaptavist", False)
    
    # TODO: REMOVE BEFORE RELEASE!!!!!!!
    setattr(config.option, "adaptavist", True)

    if adaptavist.reporter:
        adaptavist.reporter.section("ATM build meta data", bold=True)

        adaptavist.reporter.line("build_usr: %s" % (build_usr or "unknown"))
        adaptavist.reporter.line("build_url: %s" % (build_url or "unknown"))
        adaptavist.reporter.line("code_base: %s %s %s" %
                            (code_base or "unknown", (branch or "unknown") if code_base else "", (commit or "unknown") if code_base and branch else ""))
        adaptavist.reporter.line("reporting: %s" % ("enabled" if getattr(config.option, "adaptavist", False) else "disabled"))

    logger = logging.getLogger("pytest-adaptavist")
    logger_handler = logging.StreamHandler()
    logger_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(logger_handler)
    logger.propagate = False


def get_code_base_url():
    """Get current code base url."""
    code_base = None
    with suppress(subprocess.CalledProcessError):
        code_base = subprocess.check_output("git config --get remote.origin.url".split()).decode("utf-8").strip()

    return code_base

class Blocked(pytest.skip.Exception):  # pylint: disable=too-few-public-methods
    """Block exception used to abort test execution and set result status to "Blocked"."""


def pytest_addoption(parser):
    """Add options to control plugin."""

    group = parser.getgroup("adaptavist", "adaptavist test reporting")
    group.addoption("--adaptavist", action="store_true", default=False, help="Enable adaptavist reporting (default: False)")





if import_module("xdist"):
    @pytest.hookimpl(trylast=True)
    def pytest_configure_node(node):
        """This is called in case of using xdist to pass data to worker nodes."""
        node.workerinput["options"] = {"dist": node.config.option.dist, "numprocesses": node.config.option.numprocesses}

@pytest.fixture(scope="function")
def meta_data(request):
    """This can be used to store data inside of test methods."""
    return pytest.test_result_data[request.node.fullname]


@pytest.fixture(scope="function")
def meta_block(request):
    """This can be used to create reports for test blocks/steps immediately during test method call.
        ```
        with meta_block(step):
            # do your thing here
            pytest.assume(...)
        ```
    """

    def get_meta_block(step=None, timeout=META_BLOCK_TIMEOUT):
        """Return a meta block context to process single test blocks/steps."""
        return MetaBlock(request, timeout=timeout, step=step)

    return get_meta_block
    