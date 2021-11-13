import pytest


@pytest.mark.usefixtures("adaptavist_mock")
def test_restrict_user(pytester: pytest.Pytester):
    pytester.makepyfile("""
            def test_T1(meta_block):
                with meta_block():
                    with meta_block(1) as mb_1:
                        mb_1.check(True)
        """)
    pytester.makeini("""
        [pytest]
        restrict_user = abc
    """)
    report = pytester.inline_run("--adaptavist")
    assert not report._pluginmanager.get_plugin("_adaptavist").enabled
