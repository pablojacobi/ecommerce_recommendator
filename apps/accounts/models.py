"""User models for the accounts application."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser.

    Adds marketplace preferences for the recommendation system.
    """

    preferred_marketplaces: models.JSONField[list[str]] = models.JSONField(
        default=list,
        blank=True,
        help_text="List of preferred marketplace IDs (e.g., ['EBAY_US', 'MLC'])",
    )

    class Meta:
        """Meta options for User model."""

        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self) -> str:
        """Return string representation of user."""
        return self.username
