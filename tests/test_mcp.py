"""验证 MCP 工具能够被客户端发现。"""

import unittest

from mcp import Client

from server import mcp


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_expected_tools(self) -> None:
        async with Client(mcp, raise_exceptions=True) as client:
            listed = await client.list_tools()

        names = {tool.name for tool in listed.tools}
        self.assertEqual(
            names,
            {
                "tencent_docs_login",
                "tencent_docs_official_status",
                "tencent_docs_list_files",
                "tencent_docs_set_starred",
                "tencent_docs_restore_file",
                "tencent_docs_add_shortcut",
                "tencent_docs_list_versions",
                "tencent_docs_set_pinned",
                "tencent_docs_permanently_delete_trash_item",
                "tencent_docs_clear_trash",
                "tencent_docs_create_form",
                "tencent_docs_create_and_publish_form",
                "tencent_docs_inspect_form",
                "tencent_docs_replace_form_questions",
                "tencent_docs_publish_form",
                "tencent_docs_build_and_publish_form",
                "tencent_docs_openapi_status",
                "tencent_docs_openapi_setup",
                "tencent_docs_openapi_login",
                "tencent_docs_openapi_logout",
                "tencent_docs_openapi_set_starred",
                "tencent_docs_openapi_set_pinned",
                "tencent_docs_openapi_set_watermark",
                "tencent_docs_openapi_create_shortcut",
                "tencent_docs_openapi_recover_file",
                "tencent_docs_openapi_get_user_access",
                "tencent_docs_openapi_get_file_permission",
                "tencent_docs_openapi_get_folder_permission",
                "tencent_docs_openapi_transfer_ownership",
                "tencent_docs_openapi_set_file_permission",
                "tencent_docs_openapi_apply_file_permission",
                "tencent_docs_openapi_add_collaborators",
                "tencent_docs_openapi_remove_collaborator",
                "tencent_docs_openapi_list_collaborators",
                "tencent_docs_openapi_filter_files",
                "tencent_docs_openapi_convert_file_id",
                "tencent_docs_openapi_get_usage",
                "tencent_docs_openapi_get_unread_count",
                "tencent_docs_openapi_set_form_release",
                "tencent_docs_openapi_generate_form_result",
                "tencent_docs_openapi_batch_insert_sheet_images",
            },
        )
