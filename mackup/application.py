"""
Application Profile.

An Application Profile contains all the information about an application in
Mackup. Name, files, ...
"""
import os
from pathlib import Path
from typing import Set, Tuple, List

from . import utils
from .mackup import Mackup


class ApplicationProfile(object):
    """Instantiate this class with application specific data."""

    def __init__(self, mackup, app, dry_run=False, strategy="link", verbose=False):
        assert isinstance(mackup, Mackup)

        self.mackup = mackup
        self.app = app
        self.dry_run = dry_run
        self.strategy = strategy
        self.verbose = verbose

    def get_files(self, source: Path, target: Path) -> List[Tuple[Path, Path, str]]:
        """
        Get all resolved home-mackup file path tuples. The according files
        don't necessarily have to exist - this is verified elsewhere.

        Parameters
        ----------
        source: Path
                Where to resolve glob patterns from. For backups, this is the
                home directory.
        target: Path
                Where to place the source files. For backups, this is the
                mackup folder.
        """
        file_paths: Set[str] = self.app["configuration_files"]
        if self.app["enable_glob"]:
            return [
                (
                    filename.resolve(),
                    (target / filename.relative_to(source)).resolve(),
                    str(filename.relative_to(source)),
                )
                for file_path in file_paths
                for filename in source.glob(file_path)
            ]
        else:
            return [
                (
                    (source / file_path).resolve(),
                    (target / file_path).resolve(),
                    file_path,
                )
                for file_path in file_paths
            ]

    def backup(self):
        """
        Backup the application config files.

        Algorithm:
            if exists home/file
              if home/file is a real file
                if exists mackup/file
                  are you sure?
                  if sure
                    rm mackup/file
                    mv home/file mackup/file
                    link mackup/file home/file
                else
                  mv home/file mackup/file
                  link mackup/file home/file
        """

        # NOTE: Not using Path.home() for being able to use fake home
        #  directories (i.e. for testing)
        source_folder = Path(os.environ["HOME"])

        for home_filepath, mackup_filepath, filename in self.get_files(
            source=source_folder,
            target=Path(self.mackup.mackup_folder),
        ):
            # If the file exists and is not already a link pointing to Mackup
            if (os.path.isfile(home_filepath) or os.path.isdir(home_filepath)) and not (
                os.path.islink(home_filepath)
                and (os.path.isfile(mackup_filepath) or os.path.isdir(mackup_filepath))
                and os.path.samefile(home_filepath, mackup_filepath)
            ):
                if self.verbose:
                    print(
                        "Backing up\n  {}\n  to\n  {} ...".format(
                            home_filepath, mackup_filepath
                        )
                    )
                else:
                    print("Backing up {} ...".format(filename))

                if self.dry_run:
                    continue

                # Check if we already have a backup
                if os.path.exists(mackup_filepath):
                    # Name it right
                    if os.path.isfile(mackup_filepath):
                        file_type = "file"
                    elif os.path.isdir(mackup_filepath):
                        file_type = "folder"
                    elif os.path.islink(mackup_filepath):
                        file_type = "link"
                    else:
                        raise ValueError("Unsupported file: {}".format(mackup_filepath))

                    # Ask the user if he really wants to replace it
                    if utils.confirm(
                        "A {} named {} already exists in the"
                        " backup.\nAre you sure that you want to"
                        " replace it?".format(file_type, mackup_filepath)
                    ):
                        # Delete the file in Mackup
                        utils.delete(str(mackup_filepath))
                        self.backup_file(str(home_filepath), str(mackup_filepath))
                else:
                    self.backup_file(str(home_filepath), str(mackup_filepath))
            elif self.verbose:
                if os.path.exists(home_filepath):
                    print(
                        "Doing nothing\n  {}\n  "
                        "is already backed up to\n  {}".format(
                            home_filepath, mackup_filepath
                        )
                    )
                elif os.path.islink(home_filepath):
                    print(
                        "Doing nothing\n  {}\n  "
                        "is a broken link, you might want to fix it.".format(
                            home_filepath
                        )
                    )
                else:
                    print("Doing nothing\n  {}\n  does not exist".format(home_filepath))

    def backup_file(self, home_filepath: str, mackup_filepath: str):
        if self.strategy == "link":
            utils.copy(home_filepath, mackup_filepath)
            utils.delete(home_filepath)
            # Link the backed up file to its original place
            utils.link(mackup_filepath, home_filepath)
        elif self.strategy == "copy":
            utils.copy(home_filepath, mackup_filepath)
        else:
            raise ValueError("Invalid strategy {}".format(self.strategy))

    def restore(self):
        """
        Restore the application config files.

        Algorithm:
            if exists mackup/file
              if exists home/file
                are you sure?
                if sure
                  rm home/file
                  link/copy mackup/file home/file
              else
                link/copy mackup/file home/file
        """

        mackup_folder = Path(self.mackup.mackup_folder)
        home_folder = Path(os.environ["HOME"])

        for mackup_filepath, home_filepath, filename in self.get_files(
            source=mackup_folder,
            target=home_folder,
        ):
            # If the file exists and is not already pointing to the mackup file
            # and the folder makes sense on the current platform (Don't sync
            # any subfolder of ~/Library on GNU/Linux)
            file_or_dir_exists = os.path.isfile(mackup_filepath) or os.path.isdir(
                mackup_filepath
            )
            pointing_to_mackup = (
                os.path.islink(home_filepath)
                and os.path.exists(mackup_filepath)
                and os.path.samefile(mackup_filepath, home_filepath)
            )
            supported = utils.can_file_be_synced_on_current_platform(
                home_filepath.relative_to(home_folder)
            )

            if file_or_dir_exists and not pointing_to_mackup and supported:
                if self.verbose:
                    print(
                        "Restoring\n  linking {}\n  to      {} ...".format(
                            home_filepath, mackup_filepath
                        )
                    )
                else:
                    print("Restoring {} ...".format(filename))

                if self.dry_run:
                    continue

                # Check if there is already a file in the home folder
                if os.path.exists(home_filepath):
                    # Name it right
                    if os.path.isfile(home_filepath):
                        file_type = "file"
                    elif os.path.isdir(home_filepath):
                        file_type = "folder"
                    elif os.path.islink(home_filepath):
                        file_type = "link"
                    else:
                        raise ValueError("Unsupported file: {}".format(mackup_filepath))

                    if utils.confirm(
                        "You already have a {} named {} in your"
                        " home.\nDo you want to replace it with"
                        " your backup?".format(file_type, filename)
                    ):
                        utils.delete(str(home_filepath))
                        self.restore_file(str(mackup_filepath), str(home_filepath))
                else:
                    self.restore_file(str(mackup_filepath), str(home_filepath))
            elif self.verbose:
                if os.path.exists(home_filepath):
                    print(
                        "Doing nothing\n  {}\n  already linked by\n  {}".format(
                            mackup_filepath, home_filepath
                        )
                    )
                elif os.path.islink(home_filepath):
                    print(
                        "Doing nothing\n  {}\n  "
                        "is a broken link, you might want to fix it.".format(
                            home_filepath
                        )
                    )
                else:
                    print(
                        "Doing nothing\n  {}\n  does not exist".format(mackup_filepath)
                    )

    def restore_file(self, mackup_filepath: str, home_filepath: str):
        if self.strategy == "link":
            utils.link(mackup_filepath, home_filepath)
        elif self.strategy == "copy":
            utils.copy(mackup_filepath, home_filepath)
        else:
            raise ValueError("Invalid strategy {}".format(self.strategy))

    def uninstall(self):
        """
        Uninstall Mackup.

        Restore any file where it was before the 1st Mackup backup.

        Algorithm:
            for each file in config
                if mackup/file exists
                    if home/file exists
                        delete home/file
                    copy mackup/file home/file
            delete the mackup folder
            print how to delete mackup
        """

        mackup_folder = Path(self.mackup.mackup_folder)
        home_folder = Path(os.environ["HOME"])

        for mackup_filepath, home_filepath, filename in self.get_files(
            source=mackup_folder,
            target=home_folder,
        ):
            # If the mackup file exists
            if os.path.isfile(mackup_filepath) or os.path.isdir(mackup_filepath):
                # Check if there is a corresponding file in the home folder
                if os.path.exists(home_filepath):
                    if self.verbose:
                        print(
                            "Reverting {}\n  at {} ...".format(
                                mackup_filepath, home_filepath
                            )
                        )
                    else:
                        print("Reverting {} ...".format(filename))

                    if self.dry_run:
                        continue

                    # If there is, delete it as we are gonna copy the Dropbox
                    # one there
                    utils.delete(str(home_filepath))

                    # Copy the Dropbox file to the home folder
                    utils.copy(str(mackup_filepath), str(home_filepath))
            elif self.verbose:
                print("Doing nothing, {} does not exist".format(mackup_filepath))
