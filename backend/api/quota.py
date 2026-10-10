"""Per-user daily job quota (protects Google API + SageMaker spend). One counter item per user per IST day."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

IST = timezone(timedelta(hours=5, minutes=30))


class QuotaExceeded(Exception):
    pass


def consume(table, sub: str, n: int, limit: int) -> int:
    """Atomically add n jobs to today's counter; raise QuotaExceeded (and change nothing) if it would pass limit."""
    if n > limit:
        raise QuotaExceeded(f"daily limit is {limit} jobs")
    day = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        resp = table.update_item(
            Key={"pk": f"{sub}#{day}"},
            UpdateExpression="ADD #c :n SET #t = if_not_exists(#t, :ttl)",
            ConditionExpression="attribute_not_exists(#c) OR #c <= :max",
            ExpressionAttributeNames={"#c": "count", "#t": "ttl"},
            ExpressionAttributeValues={":n": n, ":max": limit - n, ":ttl": int(time.time()) + 2 * 86400},
            ReturnValues="UPDATED_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise QuotaExceeded(f"daily limit of {limit} jobs reached; try again tomorrow") from e
        raise
    return int(resp["Attributes"]["count"])
