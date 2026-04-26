import { createChartLabApi } from "./api/chartLab.js";
import { createOperationsApi } from "./api/operations.js";
import { createOperationsTradeStreamApi } from "./api/operationsTradeStream.js";
import { createPipelinesApi } from "./api/pipelines.js";
import { createServicesApi } from "./api/services.js";
import { mountChartLab } from "./chartLab.js";
import { mountOperationsCenter } from "./operationsCenter.js";
import { mountOperationsTradeStream } from "./operationsTradeStream.js";
import { mountProviders } from "./providers.js";

const operationsRoot = document.querySelector("#operations-center");
const operationsTradeStreamRoot = document.querySelector("#operations-trade-stream");
const providersRoot = document.querySelector("#providers");
const chartLabRoot = document.querySelector("#chart-lab");

if (operationsRoot) {
  mountOperationsCenter(operationsRoot, createOperationsApi());
}

if (operationsTradeStreamRoot) {
  mountOperationsTradeStream(operationsTradeStreamRoot, createOperationsTradeStreamApi());
}

if (providersRoot) {
  mountProviders(providersRoot, {
    pipelinesApi: createPipelinesApi(),
    servicesApi: createServicesApi()
  });
}

if (chartLabRoot) {
  mountChartLab(chartLabRoot, createChartLabApi());
}
