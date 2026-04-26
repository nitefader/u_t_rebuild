import { createBrokerAccountsApi } from "./api/brokerAccounts.js";
import { createChartLabApi } from "./api/chartLab.js";
import { createOperationsApi } from "./api/operations.js";
import { createOperationsTradeStreamApi } from "./api/operationsTradeStream.js";
import { createPipelinesApi } from "./api/pipelines.js";
import { createServicesApi } from "./api/services.js";
import { createSystemSettingsApi } from "./api/systemSettings.js";
import { createSystemStatusApi } from "./api/systemStatus.js";
import { createSystemStreamsApi } from "./api/systemStreams.js";
import { mountSystemStatusBadge } from "./appShell.js";
import { mountBrokers } from "./brokers.js";
import { mountChartLab } from "./chartLab.js";
import { mountOperationsCenter } from "./operationsCenter.js";
import { mountOperationsTradeStream } from "./operationsTradeStream.js";
import { mountProviders } from "./providers.js";
import { mountSettings } from "./settings.js";
import { mountSystemStreams } from "./systemStreams.js";

const operationsRoot = document.querySelector("#operations-center");
const operationsStreamsRoot = document.querySelector("#operations-streams");
const operationsTradeStreamRoot = document.querySelector("#operations-trade-stream");
const providersRoot = document.querySelector("#providers");
const chartLabRoot = document.querySelector("#chart-lab");
const brokersRoot = document.querySelector("#brokers");
const settingsRoot = document.querySelector("#settings");
const statusBadgeRoot = document.querySelector("[data-system-status]");

if (statusBadgeRoot) {
  mountSystemStatusBadge(statusBadgeRoot, createSystemStatusApi());
}

if (settingsRoot) {
  mountSettings(settingsRoot, createSystemSettingsApi());
}

if (operationsRoot) {
  mountOperationsCenter(operationsRoot, createOperationsApi());
}

if (operationsStreamsRoot) {
  mountSystemStreams(operationsStreamsRoot, createSystemStreamsApi());
}

if (operationsTradeStreamRoot) {
  mountOperationsTradeStream(operationsTradeStreamRoot, createOperationsTradeStreamApi());
}

if (providersRoot) {
  mountProviders(providersRoot, {
    pipelinesApi: createPipelinesApi(),
    servicesApi: createServicesApi(),
    systemStatusApi: createSystemStatusApi()
  });
}

if (brokersRoot) {
  mountBrokers(brokersRoot, createBrokerAccountsApi());
}

if (chartLabRoot) {
  mountChartLab(chartLabRoot, createChartLabApi());
}
