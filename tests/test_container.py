"""Tests for the dependency injection container."""

import pytest
from src.container import ServiceContainer

pytestmark = pytest.mark.unit


class TestServiceContainer:
    """FS-3.x: Service container behavior."""

    def test_register_and_resolve(self, container):
        """FS-3.1: Register and resolve a service."""
        service = {"key": "value"}
        container.register(dict, service)
        resolved = container.resolve(dict)
        assert resolved is service
        assert resolved["key"] == "value"

    def test_resolve_unregistered_raises(self, container):
        """FS-3.2: Resolving unregistered service raises KeyError."""
        with pytest.raises(KeyError, match="No service registered"):
            container.resolve(str)

    def test_has_service(self, container):
        """FS-3.1: has_service returns correct boolean."""
        assert container.has_service(dict) is False
        container.register(dict, {})
        assert container.has_service(dict) is True

    def test_unregister(self, container):
        """FS-3.1: unregister removes service."""
        container.register(dict, {"a": 1})
        assert container.unregister(dict) is True
        assert container.has_service(dict) is False

    def test_unregister_not_found(self, container):
        """FS-3.1: unregister returns False for missing service."""
        assert container.unregister(str) is False

    def test_multiple_services(self, container):
        """FS-3.1: Container handles multiple types."""
        container.register(int, 42)
        container.register(str, "hello")
        container.register(list, [1, 2, 3])
        assert container.resolve(int) == 42
        assert container.resolve(str) == "hello"
        assert container.resolve(list) == [1, 2, 3]

    def test_overwrite_registration(self, container):
        """FS-3.1: Re-registering overwrites previous value."""
        container.register(str, "first")
        container.register(str, "second")
        assert container.resolve(str) == "second"
