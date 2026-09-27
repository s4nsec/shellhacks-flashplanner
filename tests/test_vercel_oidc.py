import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from google.auth import identity_pool

from server import gemini, main


class VercelOidcTests(unittest.TestCase):
    def test_request_header_is_kept_for_gemini(self):
        with mock.patch.object(main.gemini, "vercel_oidc_token") as token:
            TestClient(main.app).get("/api/config", headers={"x-vercel-oidc-token": "vercel-jwt"})

        token.set.assert_called_once_with("vercel-jwt")

    def test_supplier_prefers_request_token_over_env(self):
        reset = gemini.vercel_oidc_token.set("from-header")
        try:
            with mock.patch.dict(os.environ, {"VERCEL_OIDC_TOKEN": "from-env"}):
                self.assertEqual("from-header", gemini.VercelOidcToken().get_subject_token(None, None))
        finally:
            gemini.vercel_oidc_token.reset(reset)

    def test_supplier_falls_back_to_env_token(self):
        with mock.patch.dict(os.environ, {"VERCEL_OIDC_TOKEN": "from-env"}):
            self.assertEqual("from-env", gemini.VercelOidcToken().get_subject_token(None, None))

    def test_client_uses_workload_identity_when_service_account_is_set(self):
        with mock.patch.object(gemini, "_client", None), \
             mock.patch.object(gemini.config, "GEMINI_API_KEY", ""), \
             mock.patch.object(gemini.config, "GCP_PROJECT_NUMBER", "123"), \
             mock.patch.object(gemini.config, "GCP_WORKLOAD_IDENTITY_POOL_ID", "vercel"), \
             mock.patch.object(gemini.config, "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID", "vercel"), \
             mock.patch.object(gemini.config, "GCP_SERVICE_ACCOUNT_EMAIL", "sa@p.iam.gserviceaccount.com"), \
             mock.patch.object(gemini.genai, "Client") as client:
            gemini.client()

        credentials = client.call_args.kwargs["credentials"]
        self.assertIsInstance(credentials, identity_pool.Credentials)
        self.assertEqual("//iam.googleapis.com/projects/123/locations/global/"
                         "workloadIdentityPools/vercel/providers/vercel", credentials._audience)
        self.assertEqual("https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
                         "sa@p.iam.gserviceaccount.com:generateAccessToken",
                         credentials._service_account_impersonation_url)

    def test_client_uses_default_credentials_without_service_account(self):
        with mock.patch.object(gemini, "_client", None), \
             mock.patch.object(gemini.config, "GCP_SERVICE_ACCOUNT_EMAIL", ""), \
             mock.patch.object(gemini.genai, "Client") as client:
            gemini.client()

        self.assertIsNone(client.call_args.kwargs["credentials"])


if __name__ == "__main__":
    unittest.main()
