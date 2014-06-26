# -*- coding: utf-8 -*-
from modularodm.validators import (
    URLValidator, MinValueValidator, MaxValueValidator
)
from modularodm.exceptions import ValidationValueError

from framework import fields
from framework.mongo.utils import sanitized

from website.addons.base import AddonNodeSettingsBase


class ForwardNodeSettings(AddonNodeSettingsBase):

    url = fields.StringField(validate=URLValidator())
    label = fields.StringField(validate=sanitized)
    redirect_bool = fields.BooleanField(default=True, validate=True)
    redirect_secs = fields.IntegerField(
        default=15,
        validate=[MinValueValidator(5), MaxValueValidator(60)]
    )

    @property
    def link_text(self):
        return self.label if self.label else self.url


@ForwardNodeSettings.subscribe('before_save')
def validate_circular_reference(schema, instance):
    """Prevent node from forwarding to itself."""
    if instance.url and instance.owner._id in instance.url:
        raise ValidationValueError('Circular URL')
