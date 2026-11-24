"""确定性规则先扫，再给行级说明。不执行被审查的代码。"""

import ast

EXPLAINS = {
    "SQL_CONCAT": "SQL 与外部输入拼在一起，调用方可以改变语句结构。应使用参数绑定。",
    "EVAL": "eval/exec 会把字符串当代码执行。审查场景里应直接删掉，改为明确的解析。",
    "BARE_EXCEPT": "空 except 会吞掉退出和键盘中断以外的所有异常，故障被藏住。",
    "SECRET": "口令或密钥写成了字面量，会进仓库和日志。应放到环境变量。",
    "SHELL": "shell=True 或 os.system 会经过系统 shell，参数里的元字符会被解释。",
    "PICKLE": "pickle 反序列化可以在加载时执行构造逻辑，不能用来解析不可信输入。",
    "SYNTAX": "代码无法解析，规则引擎没有继续往下扫。",
}

SQL_WORDS = ("select ", "insert ", "update ", "delete ", " where ")


def review_source(source: str) -> dict:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {
            "comments": [
                {
                    "line": exc.lineno or 1,
                    "rule": "SYNTAX",
                    "severity": "high",
                    "message": EXPLAINS["SYNTAX"],
                }
            ],
            "summary": "语法错误，未做规则扫描。",
        }

    comments: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"eval", "exec"}:
                _add(comments, node, "EVAL", "high")
            if name == "pickle.loads":
                _add(comments, node, "PICKLE", "high")
            if name == "os.system":
                _add(comments, node, "SHELL", "high")
            if name in {"subprocess.run", "subprocess.call", "subprocess.Popen"}:
                for kw in node.keywords:
                    if kw.arg == "shell" and _is_true(kw.value):
                        _add(comments, node, "SHELL", "high")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "format":
                if _looks_like_sql(node.func.value):
                    _add(comments, node, "SQL_CONCAT", "high")
            for arg in node.args:
                if _is_dynamic_sql(arg):
                    _add(comments, node, "SQL_CONCAT", "high")
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            _add(comments, node, "BARE_EXCEPT", "medium")
        elif isinstance(node, ast.Assign):
            if _hardcoded_secret(node):
                _add(comments, node, "SECRET", "high")
            if _is_dynamic_sql(node.value):
                _add(comments, node, "SQL_CONCAT", "high")

    comments.sort(key=lambda row: row["line"])
    deduped = []
    seen = set()
    for row in comments:
        key = (row["line"], row["rule"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    if not deduped:
        summary = "规则引擎没有命中。说明只覆盖了拼接 SQL、动态执行、空 except、硬编码口令和 shell。"
    else:
        summary = f"规则先命中 {len(deduped)} 处，下面的说明只解释这些行，没有把整段代码交给自由生成。"
    return {"comments": deduped, "summary": summary}


def _add(comments: list[dict], node: ast.AST, rule: str, severity: str) -> None:
    comments.append(
        {
            "line": getattr(node, "lineno", 1),
            "rule": rule,
            "severity": severity,
            "message": EXPLAINS[rule],
        }
    )


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    return ""


def _is_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _hardcoded_secret(node: ast.Assign) -> bool:
    names = [t.id.lower() for t in node.targets if isinstance(t, ast.Name)]
    if not any(name in {"password", "secret", "api_key", "token"} for name in names):
        return False
    return isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and len(node.value.value) >= 4


def _looks_like_sql(node: ast.AST) -> bool:
    raw = _const_text(node).lower()
    return any(word in raw for word in SQL_WORDS)


def _is_dynamic_sql(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod))
    ):
        return _looks_like_sql(node)
    return False


def _const_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_const_text(part) for part in node.values)
    if isinstance(node, ast.BinOp):
        return _const_text(node.left) + " " + _const_text(node.right)
    if isinstance(node, ast.FormattedValue):
        return " "
    return ""
