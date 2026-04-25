import { createOperationsApi } from "./api/operations.js";
import { createPipelinesApi } from "./api/pipelines.js";
import { createServicesApi } from "./api/services.js";
import { mountOperationsCenter } from "./operationsCenter.js";
import { mountProviders } from "./providers.js";

const operationsRoot = document.querySelector("#operations-center");
const providersRoot = document.querySelector("#providers");

if (operationsRoot) {
  mountOperationsCenter(operationsRoot, createOperationsApi());
}

if (providersRoot) {
  mountProviders(providersRoot, {
    pipelinesApi: createPipelinesApi(),
    servicesApi: createServicesApi()
  });
}
