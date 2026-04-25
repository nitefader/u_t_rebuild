import { createOperationsApi } from "./api/operations.js";
import { createServicesApi } from "./api/services.js";
import { mountOperationsCenter } from "./operationsCenter.js";
import { mountServicesCenter } from "./servicesCenter.js";

const root = document.querySelector("#operations-center");
const servicesRoot = document.querySelector("#services-center");

if (root) {
  mountOperationsCenter(root, createOperationsApi());
}

if (servicesRoot) {
  mountServicesCenter(servicesRoot, createServicesApi());
}
