from __future__ import annotations

import base64
import io
import json
import os
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import app


class DeepSeekKnowledgeContextTests(unittest.TestCase):
    def test_request_contains_only_retrieved_relevant_knowledge(self):
        captured = {}
        valid_response = {
            "dish_name": "测试菜",
            "standard_name": "测试菜",
            "confidence": "中",
            "summary": "按审核方案操作",
            "cookware": [],
            "ingredients": [{"name": "盐", "amount": "2g", "role": "必需", "substitutes": [], "note": ""}],
            "steps": [{"title": "操作", "action": "按步骤加热", "tools": [], "heat": "中火", "duration": "5分钟", "safety_tip": ""}],
            "tips": [],
            "assumptions": [],
        }
        response_body = {"choices": [{"message": {"content": json.dumps(valid_response, ensure_ascii=False)}}], "usage": {}}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return io.BytesIO(json.dumps(response_body, ensure_ascii=False).encode("utf-8"))

        retrieved = {
            "recipe": {
                "standard_name": "测试菜",
                "version_no": 2,
                "servings": 2,
                "serving_unit": "人份",
                "ingredients": [{"canonical_name": "盐", "amount": 2, "unit": "g", "role": "调味"}],
                "cookware": [],
                "methods": [],
                "steps": [],
                "evidence": [{"title": "已核验自有来源", "our_summary": "仅限这道菜的有效审核依据", "url": None}],
            },
            "experiences": [{"title": "这道菜的经验", "claim": "与目标菜直接相关"}],
            "unrelated_fixture_marker": "DO_NOT_SEND_UNRELATED_CONTEXT",
        }
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}), \
             patch.object(app, "local_cookbook_context", return_value=retrieved), \
             patch.object(app, "urlopen", side_effect=fake_urlopen):
            app.call_deepseek_dish_analysis("测试菜", "少盐", ["炒锅"])

        user_content = captured["payload"]["messages"][1]["content"][0]["text"]
        self.assertIn("测试菜", user_content)
        self.assertIn("已审核食材：盐 2g（调味）", user_content)
        self.assertIn("这道菜的经验", user_content)
        self.assertNotIn("DO_NOT_SEND_UNRELATED_CONTEXT", user_content)
        self.assertNotIn("可乐鸡翅", user_content)
        self.assertNotIn("稳厨已验证的标准菜名列表：", user_content)

    def test_image_payload_uses_official_image_url_data_format_without_real_api(self):
        captured = {}
        valid_response = {
            "dish_name": "测试菜", "standard_name": "测试菜", "confidence": "中",
            "summary": "按审核方案操作", "cookware": [],
            "ingredients": [{"name": "盐", "amount": "2g", "role": "必需", "substitutes": [], "note": ""}],
            "steps": [{"title": "操作", "action": "按步骤加热", "tools": [], "heat": "中火", "duration": "5分钟", "safety_tip": ""}],
            "tips": [], "assumptions": [],
        }
        response_body = {"choices": [{"message": {"content": json.dumps(valid_response, ensure_ascii=False)}}], "usage": {}}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return io.BytesIO(json.dumps(response_body, ensure_ascii=False).encode("utf-8"))

        image_bytes = b"\x89PNG\r\n\x1a\nmock-image-bytes"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}), \
             patch.object(app, "local_cookbook_context", return_value={}), \
             patch.object(app, "urlopen", side_effect=fake_urlopen) as mocked_urlopen:
            app.call_deepseek_dish_analysis("测试菜", "少盐", ["炒锅"], image_bytes=image_bytes, image_mime="image/png")

        self.assertEqual(mocked_urlopen.call_count, 1)
        payload = captured["payload"]
        self.assertEqual(payload["model"], "deepseek-flash")
        content = payload["messages"][1]["content"]
        self.assertEqual([part["type"] for part in content], ["text", "image_url"])
        self.assertEqual(content[1]["image_url"]["url"],
                         "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii"))
        self.assertEqual(content[1]["image_url"]["detail"], "auto")

    def test_http_error_is_reported_without_exposing_provider_response(self):
        http_error = HTTPError("https://api.deepseek.com/chat/completions", 400, "Bad Request", {}, io.BytesIO(b"provider detail"))
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-key"}), \
             patch.object(app, "local_cookbook_context", return_value={}), \
             patch.object(app, "urlopen", side_effect=http_error):
            with self.assertRaisesRegex(app.DishAnalysisError, "DeepSeek 暂时没有完成分析") as error:
                app.call_deepseek_dish_analysis("测试菜", "", [])
        self.assertNotIn("provider detail", str(error.exception))


if __name__ == "__main__":
    unittest.main()
