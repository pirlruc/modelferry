"""Show how an inference package consumes model-fetcher.

The functions below are the integration boundary. They return a filesystem path. Loading that
path with joblib, PyTorch, ONNX Runtime, or scikit-learn belongs to the caller. Those imports are
intentionally absent from this file.
"""

from pathlib import Path

from model_fetcher import ModelFetcher


def fetch_direct(project_id: str, model_name: str, version: str, file_name: str) -> Path:
    """Download one known model version.

    Args:
        project_id: GitLab project id or path.
        model_name: Model or generic package name.
        version: Artifact version.
        file_name: File to store locally.

    Returns:
        Path of the verified local file.
    """
    with ModelFetcher() as fetcher:
        return fetcher.download_model(
            project_id=project_id,
            model_name=model_name,
            version=version,
            file_name=file_name,
        )


def fetch_from_flag(project_id: str, flag_name: str, user_id: str, environment: str) -> Path:
    """Download the model named by a feature flag.

    Args:
        project_id: Project that owns the flag.
        flag_name: Flag whose payload contains ``model_name`` and ``version``.
        user_id: Evaluation user id.
        environment: GitLab environment name.

    Returns:
        Path of the verified local file.
    """
    with ModelFetcher() as fetcher:
        return fetcher.download_from_feature_flag(
            project_id=project_id,
            flag_name=flag_name,
            context={"user_id": user_id, "environment": environment},
        )


def hand_to_caller_runtime(model_path: Path) -> Path:
    """Give a downloaded artifact to the inference runtime.

    model-fetcher does not open the file. The application that called
    :func:`fetch_direct` or :func:`fetch_from_flag` loads it, for example::

        import joblib

        estimator = joblib.load(model_path)

    Args:
        model_path: Path returned by model-fetcher.

    Returns:
        The same path after checking that the file exists.

    Raises:
        FileNotFoundError: If the artifact is not on disk.
    """
    if not model_path.is_file():
        raise FileNotFoundError(model_path)

    return model_path
