from ananta.explorers.document import config


def test_upload_limits_have_expected_values():
    assert config.MAX_UPLOAD_BYTES == 50 * 1024 * 1024
    assert config.MAX_AGGREGATE_UPLOAD_BYTES == 200 * 1024 * 1024
    assert config.MAX_FOLDER_FILES == 500
    assert config.SOFT_WARN_FOLDER_FILES == 100
    assert config.TARGET_BATCH_BYTES == 50 * 1024 * 1024
