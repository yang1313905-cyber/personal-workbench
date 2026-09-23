"""指数退避重试工具。网络类操作统一走这里。"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

log = logging.getLogger("workbench.retry")


def retry(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    delay: float = 2.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    what: str = "操作",
) -> Any:
    """执行 fn，失败按指数退避重试，全部失败后抛出最后一次异常。

    :param attempts: 最多尝试次数（含首次）
    :param delay: 首次重试前等待秒数
    :param backoff: 每次重试等待翻倍系数
    """
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as e:  # noqa: BLE001
            last = e
            if i >= attempts:
                break
            wait = delay * (backoff ** (i - 1))
            log.warning("%s 第 %d/%d 次失败: %s；%.1fs 后重试", what, i, attempts, e, wait)
            time.sleep(wait)
    assert last is not None
    raise last
