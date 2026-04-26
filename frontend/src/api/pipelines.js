const PREFIX = "/api/v1/market-data";

async function requestJson(url, options = {}, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") {
    throw new Error("Pipelines API unavailable: fetch is not configured");
  }
  const response = await fetchImpl(url, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(options.headers || {})
    },
    ...options
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(`Pipelines API request failed (${response.status}): ${detail}`);
  }
  return payload;
}

export function createPipelinesApi(fetchImpl = globalThis.fetch) {
  const get = (path) => requestJson(`${PREFIX}${path}`, {}, fetchImpl);
  const post = (path, body) => requestJson(`${PREFIX}${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined }, fetchImpl);
  const put = (path, body) => requestJson(`${PREFIX}${path}`, { method: "PUT", body: JSON.stringify(body) }, fetchImpl);
  return {
    listPipelines: () => get("/pipelines"),
    createPipeline: (payload) => post("/pipelines", payload),
    createPipelineFromService: (payload) => post("/pipelines/from-service", payload),
    updatePipeline: (id, payload) => put(`/pipelines/${id}`, payload),
    setDefaultPipeline: (id) => post(`/pipelines/${id}/set-default`),
    disablePipeline: (id) => post(`/pipelines/${id}/disable`),
    bootstrapFromEnv: () => post("/bootstrap-from-env")
  };
}
