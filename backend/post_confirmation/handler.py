"""Cognito post-confirmation trigger: every new user starts in the Homeowner group.
Installers are promoted by hand for the demo (infra/scripts/make_installer.sh)."""
from __future__ import annotations

import os

import boto3

DEFAULT_GROUP = os.environ.get("DEFAULT_GROUP", "Homeowner")


def handler(event, context):
    if event.get("triggerSource") == "PostConfirmation_ConfirmSignUp":
        boto3.client("cognito-idp").admin_add_user_to_group(
            UserPoolId=event["userPoolId"], Username=event["userName"], GroupName=DEFAULT_GROUP)
    return event
