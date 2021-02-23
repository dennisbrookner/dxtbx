import json
import os
import warnings

from dxtbx.model.crystal import CrystalFactory
from dxtbx.serialize.imageset import imageset_from_dict


def imageset_from_string(string, directory=None):
    """Load the string and return the models.

    Params:
        string The JSON string to load

    Returns:
        The models

    """
    warnings.warn(
        "This function is deprecated and will be removed in the next release",
        DeprecationWarning,
        stacklevel=2,
    )

    return imageset_from_dict(json.loads(string), directory=directory)


def imageset(filename):
    """Load the given JSON file.

    Params:
        infile The input filename

    Returns:
        The models

    """
    # If the input is a string then open and read from that file
    filename = os.path.abspath(filename)
    directory = os.path.dirname(filename)
    with open(filename, "r") as infile:
        return imageset_from_dict(json.load(infile), directory=directory)


def datablock(filename, check_format=True):
    """Load a given JSON or pickle file.

    Params:
      filename The input filename

    Returns:
      The datablock

    """
    # Resolve recursive import
    from dxtbx.datablock import DataBlockFactory

    return DataBlockFactory.from_serialized_format(filename, check_format=check_format)


def crystal(infile):
    """Load the given JSON file.

    Params:
        infile The input filename or file object

    Returns:
        The models

    """
    # If the input is a string then open and read from that file
    if isinstance(infile, str):
        with open(infile, "r") as infile:
            return CrystalFactory.from_dict(json.loads(infile.read()))

    # Otherwise assume the input is a file and read from it
    else:
        return CrystalFactory.from_dict(json.loads(infile.read()))


def experiment_list(infile, check_format=True):
    """Load an experiment list from a serialized format."""
    # Resolve recursive import
    from dxtbx.model.experiment_list import ExperimentListFactory

    if infile and hasattr(infile, "__fspath__"):
        infile = (
            infile.__fspath__()
        )  # Resolve file system path (PEP-519) object to string.

    return ExperimentListFactory.from_serialized_format(
        infile, check_format=check_format
    )
