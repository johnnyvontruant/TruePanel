"""
Persistent JSON archive for protocol-discovery experiments and runs.
"""

from __future__ import annotations

import json
from pathlib import Path


class ProtocolArchive:
    def __init__(
        self,
        directory="development/protocol",
    ):
        self.directory = Path(directory)

    def ensure_directory(self):
        self.directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _safe_name(value):
        value = str(value).strip()

        if not value:
            raise ValueError(
                "archive name is required"
            )

        safe = "".join(
            character
            if character.isalnum()
            or character in "-_"
            else "-"
            for character in value
        )

        safe = safe.strip("-")

        if not safe:
            raise ValueError(
                "archive name contains no usable characters"
            )

        return safe

    def experiment_path(self, experiment):
        name = self._safe_name(
            experiment.name
        )

        return self.directory / (
            f"{name}_{experiment.experiment_id}.experiment.json"
        )

    def run_path(self, run):
        experiment = run.experiment
        name = self._safe_name(
            experiment.name
        )

        return self.directory / (
            f"{name}_{experiment.experiment_id}.run.json"
        )

    def save_experiment(self, experiment):
        self.ensure_directory()
        path = self.experiment_path(
            experiment
        )

        path.write_text(
            json.dumps(
                experiment.as_dict(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return path

    def save_run(self, run):
        self.ensure_directory()
        path = self.run_path(run)

        path.write_text(
            json.dumps(
                run.as_dict(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        return path

    @staticmethod
    def load(path):
        path = Path(path)

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    def list_experiments(self):
        if not self.directory.exists():
            return ()

        return tuple(
            sorted(
                self.directory.glob(
                    "*.experiment.json"
                )
            )
        )

    def list_runs(self):
        if not self.directory.exists():
            return ()

        return tuple(
            sorted(
                self.directory.glob(
                    "*.run.json"
                )
            )
        )
