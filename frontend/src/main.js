import { createOperationsApi } from "./api/operations.js";
import { mountOperationsCenter } from "./operationsCenter.js";

const root = document.querySelector("#operations-center");

if (root) {
  mountOperationsCenter(root, createOperationsApi());
}
