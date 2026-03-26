import json
import base64
import zlib
import pickle
import sys
import os

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_current_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from lcb_runner.evaluation.compute_code_generation_metrics import check_correctness
except ImportError as e:
    print(f"Error importing lcb_runner: {e}")
    print(f"Current sys.path: {sys.path}")
    raise




def normalize_test_cases(raw_data, depth=0):
    """Auto-translated documentation for normalize_test_cases."""
    if depth > 3:
        return []


    cases = []

    if isinstance(raw_data, list):
        return raw_data

    elif isinstance(raw_data, str):
        try:
            new_data = json.loads(raw_data)
            return normalize_test_cases(new_data, depth + 1)
        except json.JSONDecodeError:
            return []

    elif isinstance(raw_data, dict):
        for k, v in raw_data.items():
            if isinstance(v, (dict, list)):
                extracted = normalize_test_cases(v, depth + 1)
                cases.extend(extracted)
        return cases

    return cases


def evaluate_codeforces_sample(sample_data, generated_code, use_private=True, timeout=5):
    inputs_list = []
    outputs_list = []


    # --- 1. Public Cases ---
    try:
        public_raw = sample_data.get('public_test_cases', '[]')
        if public_raw:
            public_cases = json.loads(public_raw)
            for case in public_cases:
                inputs_list.append(case.get('input', case.get('inputs')))
                outputs_list.append(case.get('output', case.get('outputs')))
    except Exception as e:
        print(f"Warning: public-case parsing failed: {e}")

    # --- 2. Private Cases ---
    if use_private and sample_data.get('private_test_cases'):
        raw_private = sample_data['private_test_cases']
        parsed_obj = None

        try:
            # 1. Base64
            b64_bytes = base64.b64decode(raw_private)
            # 2. Zlib
            try:
                decompressed = zlib.decompress(b64_bytes)
            except zlib.error:
                decompressed = b64_bytes

            # 3. Pickle / JSON
            try:
                parsed_obj = pickle.loads(decompressed)
            except:
                try:
                    parsed_obj = json.loads(decompressed.decode('utf-8'))
                except Exception as e:
                    print(f"   Failure: parsing failed completely: {e}")

        except Exception as e:
            print(f"Warning: decryption failed: {e}")

        if parsed_obj is not None:
            private_cases = normalize_test_cases(parsed_obj)

            valid_count = 0
            for case in private_cases:
                if not isinstance(case, dict): continue
                inp = case.get('input') or case.get('inputs')
                out = case.get('output') or case.get('outputs')
                if inp is not None and out is not None:
                    inputs_list.append(inp)
                    outputs_list.append(out)
                    valid_count += 1

            # if valid_count > 0:

    if not inputs_list:
        return {
            "passed": False,
            "passed_count": 0,
            "total_count": 0,
            "error_info": ["Error: no valid test cases were loaded (No valid test cases found)"]
        }




    # if len(inputs_list) > 0:

    lcb_payload = {
        "inputs": inputs_list,
        "outputs": outputs_list,
        "fn_name": None
    }
    final_sample = {"input_output": json.dumps(lcb_payload)}


    try:
        results, metadata = check_correctness(
            sample=final_sample,
            generation=generated_code,
            timeout=timeout,
            debug=False
        )
    except Exception as e:
        return {
            "passed": False,
            "passed_count": 0,
            "total_count": len(inputs_list),
            "error_info": [f"Evaluator runtime crash (Runner Exception): {str(e)}"]
        }

    total = len(results)
    passed_count = results.count(True)
    is_passed = (passed_count == total) and (total > 0)

    error_info = []
    if not is_passed:
        for idx, res in enumerate(results):
            if res is True:
                continue

            status = "Unknown Error"
            if res == -1:
                status = "Global Timeout"
            elif res == -2:
                status = "Wrong Answer"
            elif res == -3:
                status = "Time Limit Exceeded"
            elif res == -4:
                status = "Runtime Error"

            detail = ""
            if isinstance(metadata, list) and idx < len(metadata):
                meta = metadata[idx]
                if isinstance(meta, dict) and "error" in meta:
                    detail = f" -> {meta['error'][:100]}..."

            error_info.append(f"Case {idx + 1}: {status}{detail}")


    return {
        "passed": is_passed,
        "passed_count": passed_count,
        "total_count": total,
        "error_info": error_info
    }
