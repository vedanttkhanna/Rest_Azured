"""Core: jobs bucket, DynamoDB tables, Cognito, alerts topic, budget."""
from __future__ import annotations

from aws_cdk import Annotations, Aws, CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

from stacks.common import py_function
from stacks.config import Config
from stacks.packaging import python_asset

GROUPS = ("Homeowner", "Installer")
BUDGET_ALERTS_USD = (25, 75, 150)  # actual spend, credits excluded


class CoreStack(Stack):
    def __init__(self, scope: Construct, id: str, *, cfg: Config, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.bucket = s3.Bucket(
            self, "JobsBucket",
            bucket_name=f"solarrooftop-jobs-{Aws.ACCOUNT_ID}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            lifecycle_rules=[s3.LifecycleRule(prefix="jobs/", expiration=Duration.days(30))],
            cors=[s3.CorsRule(allowed_methods=[s3.HttpMethods.GET], allowed_origins=cfg.web_origins,
                              allowed_headers=["*"], max_age=3600)],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        self.jobs_table = ddb.Table(
            self, "JobsTable",
            table_name="Jobs",
            partition_key=ddb.Attribute(name="owner_sub", type=ddb.AttributeType.STRING),
            sort_key=ddb.Attribute(name="job_id", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.jobs_table.add_global_secondary_index(
            index_name="job_id-index",
            partition_key=ddb.Attribute(name="job_id", type=ddb.AttributeType.STRING),
        )
        self.quota_table = ddb.Table(
            self, "QuotaTable",
            table_name="Quotas",
            partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # --- Cognito: email sign-in, Homeowner/Installer groups, new users -> Homeowner
        post_confirm = py_function(
            self, "PostConfirmationFn",
            asset=python_asset("post_confirmation", {"handler.py": "backend/post_confirmation/handler.py"}),
            handler="handler.handler", environment={"DEFAULT_GROUP": "Homeowner"},
            description="Adds new users to the Homeowner group",
        )
        # Wildcard pool ARN: referencing the pool here would create a pool <-> trigger dependency cycle.
        post_confirm.add_to_role_policy(iam.PolicyStatement(
            actions=["cognito-idp:AdminAddUserToGroup"],
            resources=[f"arn:aws:cognito-idp:{Aws.REGION}:{Aws.ACCOUNT_ID}:userpool/*"],
        ))
        self.user_pool = cognito.UserPool(
            self, "UserPool",
            user_pool_name="solarrooftop-users",
            feature_plan=cognito.FeaturePlan.LITE,
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(email=cognito.StandardAttribute(required=True, mutable=True)),
            password_policy=cognito.PasswordPolicy(min_length=8, require_symbols=False),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            lambda_triggers=cognito.UserPoolTriggers(post_confirmation=post_confirm),
            removal_policy=RemovalPolicy.DESTROY,
        )
        for group in GROUPS:
            cognito.CfnUserPoolGroup(self, f"{group}Group", user_pool_id=self.user_pool.user_pool_id,
                                     group_name=group, description=f"{group} accounts")
        self.user_pool_client = self.user_pool.add_client(
            "WebClient",
            user_pool_client_name="solarrooftop-web",
            generate_secret=False,
            # SRP for the web app (Amplify); admin password auth only for infra/scripts/smoke.py (needs IAM creds).
            auth_flows=cognito.AuthFlow(user_srp=True, admin_user_password=True),
            prevent_user_existence_errors=True,
        )

        # --- Alerts: SNS topic for pipeline-failure alarms + budget with credits excluded
        self.alerts_topic = sns.Topic(self, "AlertsTopic", topic_name="solarrooftop-alerts")
        for email in cfg.alert_emails:
            self.alerts_topic.add_subscription(subs.EmailSubscription(email))
        if cfg.alert_emails:
            subscribers = [budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=e)
                           for e in cfg.alert_emails[:10]]
            notifications = [
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type=kind, comparison_operator="GREATER_THAN",
                        threshold=amount, threshold_type="ABSOLUTE_VALUE"),
                    subscribers=subscribers)
                for kind, amount in [*(("ACTUAL", a) for a in BUDGET_ALERTS_USD), ("FORECASTED", 150)]
            ]
            budgets.CfnBudget(
                self, "CreditBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="solarrooftop-credits",
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=200, unit="USD"),
                    # Credits would otherwise net the spend to $0 and no alert would ever fire.
                    cost_types=budgets.CfnBudget.CostTypesProperty(include_credit=False, include_refund=False),
                ),
                notifications_with_subscribers=notifications,
            )
        else:
            Annotations.of(self).add_warning(
                "No alert e-mails: budget + failure alerts NOT created. Set SOLAR_ALERT_EMAILS=a@x,b@y before deploying.")

        CfnOutput(self, "Region", value=Aws.REGION)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
