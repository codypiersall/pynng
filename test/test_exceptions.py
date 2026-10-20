"""Tests for the pynng exception dispatch system.

Validates that check_err() correctly maps NNG error codes to the appropriate
exception classes, that all exceptions have proper attributes, and that the
exception hierarchy is sound.
"""

import pytest

from pynng._nng import lib
from pynng import exceptions


class TestCheckErrSuccess:
    """Verify check_err returns None on success (error code 0)."""

    def test_check_err_returns_none_on_success(self):
        result = exceptions.check_err(0)
        assert result is None


class TestCheckErrMapping:
    """Verify check_err raises the correct exception class for each NNG error."""

    ERROR_MAP_CASES = [
        (lib.NNG_EINTR, exceptions.Interrupted),
        (lib.NNG_ENOMEM, exceptions.NoMemory),
        (lib.NNG_EINVAL, exceptions.InvalidOperation),
        (lib.NNG_EBUSY, exceptions.Busy),
        (lib.NNG_ETIMEDOUT, exceptions.Timeout),
        (lib.NNG_ECONNREFUSED, exceptions.ConnectionRefused),
        (lib.NNG_ECLOSED, exceptions.Closed),
        (lib.NNG_EAGAIN, exceptions.TryAgain),
        (lib.NNG_ENOTSUP, exceptions.NotSupported),
        (lib.NNG_EADDRINUSE, exceptions.AddressInUse),
        (lib.NNG_ESTATE, exceptions.BadState),
        (lib.NNG_ENOENT, exceptions.NoEntry),
        (lib.NNG_EPROTO, exceptions.ProtocolError),
        (lib.NNG_EUNREACHABLE, exceptions.DestinationUnreachable),
        (lib.NNG_EADDRINVAL, exceptions.AddressInvalid),
        (lib.NNG_EPERM, exceptions.PermissionDenied),
        (lib.NNG_EMSGSIZE, exceptions.MessageTooLarge),
        (lib.NNG_ECONNRESET, exceptions.ConnectionReset),
        (lib.NNG_ECONNABORTED, exceptions.ConnectionAborted),
        (lib.NNG_ECANCELED, exceptions.Canceled),
        (lib.NNG_ENOFILES, exceptions.OutOfFiles),
        (lib.NNG_ENOSPC, exceptions.OutOfSpace),
        (lib.NNG_EEXIST, exceptions.AlreadyExists),
        (lib.NNG_EREADONLY, exceptions.ReadOnly),
        (lib.NNG_EWRITEONLY, exceptions.WriteOnly),
        (lib.NNG_ECRYPTO, exceptions.CryptoError),
        (lib.NNG_EPEERAUTH, exceptions.AuthenticationError),
        (lib.NNG_ENOARG, exceptions.NoArgument),
        (lib.NNG_EAMBIGUOUS, exceptions.Ambiguous),
        (lib.NNG_EBADTYPE, exceptions.BadType),
        (lib.NNG_EINTERNAL, exceptions.Internal),
    ]

    @pytest.mark.parametrize(
        "err_code,expected_class",
        ERROR_MAP_CASES,
        ids=[c[1].__name__ for c in ERROR_MAP_CASES],
    )
    def test_check_err_maps_to_correct_exception(self, err_code, expected_class):
        with pytest.raises(expected_class):
            exceptions.check_err(err_code)


class TestExceptionAttributes:
    """Verify that raised exceptions carry the correct errno attribute."""

    def test_exception_has_errno(self):
        try:
            exceptions.check_err(lib.NNG_ETIMEDOUT)
        except exceptions.Timeout as e:
            assert e.errno == lib.NNG_ETIMEDOUT
        else:
            pytest.fail("Expected Timeout")

    def test_exception_has_string_message(self):
        try:
            exceptions.check_err(lib.NNG_ETIMEDOUT)
        except exceptions.Timeout as e:
            msg = str(e)
            assert msg == "Timed out"
        else:
            pytest.fail("Expected Timeout")


class TestExceptionHierarchy:
    """Verify the exception class hierarchy is consistent."""

    def test_all_mapped_exceptions_inherit_from_nng_exception(self):
        for exc_class in exceptions.EXCEPTION_MAP.values():
            assert issubclass(exc_class, exceptions.NNGException), (
                f"{exc_class.__name__} does not inherit from NNGException"
            )

    def test_nng_exception_inherits_from_exception(self):
        assert issubclass(exceptions.NNGException, Exception)

    def test_message_state_error_inherits_from_exception(self):
        assert issubclass(exceptions.MessageStateError, Exception)

    def test_message_state_error_is_not_nng_exception(self):
        # MessageStateError is a separate hierarchy from NNGException
        assert not issubclass(exceptions.MessageStateError, exceptions.NNGException)


class TestExceptionMapCompleteness:
    """Verify that EXCEPTION_MAP covers all commonly-encountered NNG errors."""

    def test_exception_map_has_unique_classes(self):
        """Each error code maps to a distinct exception class."""
        classes = list(exceptions.EXCEPTION_MAP.values())
        assert len(classes) == len(set(classes)), (
            "EXCEPTION_MAP has duplicate exception classes"
        )

    def test_exception_map_matches_class_count(self):
        """Every declared exception subclass (except MessageStateError) is in the map."""
        declared = {
            name: obj
            for name, obj in vars(exceptions).items()
            if isinstance(obj, type)
            and issubclass(obj, exceptions.NNGException)
            and obj is not exceptions.NNGException
        }
        mapped = set(exceptions.EXCEPTION_MAP.values())
        for name, cls in declared.items():
            assert cls in mapped, (
                f"{name} is declared but not in EXCEPTION_MAP"
            )


class TestUnknownErrorCode:
    """Verify behavior for error codes not in EXCEPTION_MAP."""

    def test_check_err_unknown_code_raises_nng_exception(self):
        with pytest.raises(exceptions.NNGException):
            exceptions.check_err(99999)

    def test_check_err_unknown_code_is_not_subclass(self):
        """Unknown codes should raise base NNGException, not a subclass."""
        try:
            exceptions.check_err(99999)
        except exceptions.NNGException as e:
            assert type(e) is exceptions.NNGException
        else:
            pytest.fail("Expected NNGException")
