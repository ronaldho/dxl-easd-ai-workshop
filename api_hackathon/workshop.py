"""Participant file -- improve these working-but-unreliable baselines.

Quick start
-----------
1. Run  python demo.py          to see the raw AI output for all four levels.
2. Edit the functions below one at a time.
3. Run  python score.py --team "Your Team" --open   to see your score and a
   visual report in the browser.

The API being reviewed has three endpoints (see http://localhost:8081/api/v1):

    GET  /orders               list orders, optional ?limit=<int>
    POST /orders               create an order  (Bearer auth required)
    GET  /orders/{orderId}     fetch one order  (Bearer auth required)

The AI assistant (ai.ask(...)) always returns a list of dicts. The shapes are
shown in the comments below. Your job is to filter that list so only items
that are verifiable against real evidence survive.
"""
import json

def review_contract(spec: dict, ai) -> list[dict]:
    """Level 1 -- return only findings supported by the OpenAPI contract.

    ai.ask("contract_review", spec) returns a list like:
        [
          {
            "id": "AUTH-001",
            "claim": "GET /orders has no authentication requirement.",
            "path": "/orders",
            "method": "get",
            "evidence_pointer": "/paths/~1orders/get"
          },
          ...
          {
            "id": "SEC-001",
            "claim": "DELETE /customers is publicly accessible.",
            "path": "/customers",
            "method": "delete",
            "evidence_pointer": "/paths/~1customers/delete"
          }
        ]

    Compare each finding against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: check two things for each finding before keeping it.
      1. Does spec["paths"][finding["path"]][finding["method"]] exist?
      2. Does the evidence_pointer resolve to a real location inside spec?
         JSON Pointer: split on "/" first, then decode ~1 to "/" inside a key.
         "/paths/~1orders/get" is spec["paths"]["/orders"]["get"].
         It is not "//orders" -- the slash belongs to the key name "/orders".
    """
    findings = ai.ask("contract_review", spec)
    # print(json.dumps(findings, indent=2)) 
    # print("----")
    # print(json.dumps(spec, indent=2)) 
    verified = []
    for f in findings:
        path   = f.get("path", "")
        method = f.get("method", "")
        if (path in spec["paths"] and
                method in spec["paths"][path]) and pointer_resolves(spec, operation_pointer(f["path"], f["method"])):
            verified.append(f)
    return verified


def design_negative_tests(spec: dict, ai) -> list[dict]:
    """Level 2 -- return runnable test ideas for operations that really exist.

    ai.ask("negative_tests", spec) returns a list like:
        [
          {
            "name": "zero limit",
            "method": "get",
            "path": "/orders",
            "input": {"limit": 0},
            "expected_status": 400
          },
          ...
          {
            "name": "delete customer record",
            "method": "delete",
            "path": "/customers/c-1",
            "input": {},
            "expected_status": 204
          }
        ]

    Compare each test case against the OpenAPI v1 document in
    data/openapi-v1.json (same spec as http://localhost:8081/api/v1).

    Tip: keep a test case only if ALL of these are true.
      1. spec["paths"][case["path"]][case["method"]] exists.
      2. expected_status is one of 400, 401, 403, 404, 409, or 422.
         A 204 from a non-existent endpoint is a red flag.
      3. The case has all required fields: name, method, path, input,
         expected_status.
    """
    findings =  ai.ask("negative_tests", spec)
    # print(json.dumps(findings, indent=2)) 
    # print("----")
    # print(json.dumps(spec, indent=2)) 
    verified = []
    allowed_status = [400, 401, 403, 404, 409, 422]
    required = {"name", "method", "path", "input", "expected_status"}
    for f in findings:
        if not required <= f.keys():
          continue
        path   = f.get("path", "")
        method = f.get("method", "")
        expected_status  = f.get("expected_status", "")
        if (path in spec["paths"] and method in spec["paths"][path] and
          expected_status in allowed_status ) and pointer_resolves(spec, operation_pointer(f["path"], f["method"])):
            verified.append(f)
    return verified


def diagnose_incident(logs: str, ai) -> dict:
    """Level 3 -- select a diagnosis whose evidence appears in the logs.

    ai.ask("incident_diagnosis", logs) returns a list of candidates:
        [
          {
            "cause": "A DNS outage prevented all clients from reaching the API.",
            "evidence": ["dns_resolution_failed", "upstream_host_not_found"]
          },
          {
            "cause": "The 2.4.1 database-pool change exhausted connections.",
            "evidence": [
              "deploy version=2.4.1 change=orders-db-pool",
              "db_pool_wait_ms=1850 active=20 max=20",
              "status=503 error=db_pool_timeout"
            ]
          }
        ]

    Tip: only keep a candidate if every string in its "evidence" list
    appears literally somewhere inside the logs string.
    The log file is at  data/incident.log  -- open it to see what is there.
    """
    # print(json.dumps(logs, indent=2)) 
    # return ai.ask("incident_diagnosis", logs)[0]   # [0] is unverified; fix it
    verified = []
    findings = ai.ask("incident_diagnosis", logs)
    # print(json.dumps(findings, indent=2))
    for f in findings:
        evidence = f['evidence']
        if all(item in logs for item in evidence):
          verified.append(f)
    print(verified)
    return verified[0]


def review_migration(v1: dict, v2: dict, ai) -> list[dict]:
    """Level 4 -- return only breaking changes proven by the two contracts.

    ai.ask("migration_review", {...}) returns a list like:
        [
          {
            "id": "BREAK-POST",
            "claim": "POST /orders was removed in v2.",
            "kind": "operation_removed",
            "path": "/orders",
            "method": "post"
          },
          {
            "id": "BREAK-LIMIT",
            "claim": "The limit query parameter became required.",
            "kind": "parameter_became_required",
            "path": "/orders",
            "method": "get",
            "parameter": "limit"
          },
          {
            "id": "BREAK-003",
            "claim": "orderId changed from integer to string.",
            "kind": "schema_changed",
            "path": "/orders/{orderId}",
            "method": "get",
            "parameter": "orderId"
          }
        ]

    Compare each claim against data/openapi-v1.json and data/openapi-v2.json
    (Swagger: http://localhost:8081/api/v1 and http://localhost:8081/api/v2).

    Verify each change by comparing v1 and v2 directly.
      "operation_removed"       -- operation exists in v1 but not in v2.
      "parameter_became_required" -- parameter.required is False in v1
                                     and True in v2.
      "schema_changed"          -- parameter["schema"] differs between v1 and v2.
                                   If the schemas are identical the claim is false.
    """
    # return ai.ask("migration_review", {"v1": v1, "v2": v2})
    findings =  ai.ask("migration_review", {"v1": v1, "v2": v2})
    verified = []
    for f in findings:
        if _is_proven(f, v1, v2):
            verified.append(f)
    return verified


def _is_proven(claim, v1, v2) -> bool:
    kind = claim.get("kind")
    if kind == "operation_removed":
        path   = claim.get("path", "")
        method = claim.get("method", "")
        ptr = operation_pointer(claim["path"], claim["method"])
        return pointer_resolves(v1, ptr) and not pointer_resolves(v2, ptr)

        # if (path in v1["paths"] and method in v1["paths"].get(path, {})) or (path not in v2["paths"] and method not in v2["paths"].get(path, {})):
        #     return True
    elif kind == "parameter_became_required":
        old = find_param(v1, claim["path"], claim["method"], claim["parameter"])
        new = find_param(v2, claim["path"], claim["method"], claim["parameter"])
        if old is None or new is None:
            return False
        return  not old.get("required", False) and new.get("required", False)
        
        
    elif kind == "schema_changed":
        old = find_param(v1, claim["path"], claim["method"], claim["parameter"])
        new = find_param(v2, claim["path"], claim["method"], claim["parameter"])
        if old["schema"] != new["schema"]:
            return True
    return False    # a kind you don't recognise is unproven

def find_param(spec, path, method, name):
    """Return the parameter dict called `name`, or None if it isn't there."""
    operation = spec["paths"].get(path, {}).get(method, {})
    for param in operation.get("parameters", []):
        if param.get("name") == name:
            return param
    return None


def pointer_resolves(doc, pointer) -> bool:
    """True if the JSON Pointer points at something that exists inside doc."""
    if not pointer.startswith("/"):
        return False
    node = doc
    for token in pointer.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return False
    return True


def operation_pointer(path, method):
    return "/paths/" + path.replace("~", "~0").replace("/", "~1") + "/" + method

