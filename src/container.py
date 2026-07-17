#!/usr/bin/env python3
"""
Simple dependency injection container
"""

from typing import TypeVar, Type, Dict, Any, Optional
from dataclasses import dataclass, field

T = TypeVar("T")


@dataclass
class ServiceContainer:
    """Simple dependency injection container"""

    _services: Dict[Type[Any], Any] = field(default_factory=dict)

    def register(self, interface: Type[T], implementation: T) -> None:
        """
        Register a service implementation for an interface

        Args:
            interface: The protocol/interface type
            implementation: The concrete implementation instance
        """
        self._services[interface] = implementation

    def resolve(self, interface: Type[T]) -> T:
        """
        Resolve a service implementation for an interface

        Args:
            interface: The protocol/interface type to resolve

        Returns:
            The registered implementation instance

        Raises:
            KeyError: If no implementation is registered for the interface
        """
        if interface not in self._services:
            raise KeyError(f"No service registered for interface: {interface}")

        return self._services[interface]

    def has_service(self, interface: Type[T]) -> bool:
        """
        Check if a service is registered for an interface

        Args:
            interface: The protocol/interface type to check

        Returns:
            True if a service is registered, False otherwise
        """
        return interface in self._services

    def unregister(self, interface: Type[T]) -> bool:
        """
        Unregister a service for an interface

        Args:
            interface: The protocol/interface type to unregister

        Returns:
            True if unregistered, False if not found
        """
        if interface in self._services:
            del self._services[interface]
            return True
        return False
