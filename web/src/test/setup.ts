// Vitest setup global.
//
// 1. Matchers de jest-dom contra el expect() de vitest. El import por el
//    subpath `/vitest` ES el que augmenta el tipo de Assertion para que
//    `expect(el).toBeInTheDocument()` (y compañía) compile y corra.
// 2. cleanup() manual entre tests. Cuando NO usamos `globals: true` en
//    vitest.config, @testing-library/react no auto-registra cleanup
//    contra el afterEach global y los tests acumulan DOM (el render del
//    test N+1 se monta encima del N, getByRole encuentra múltiples
//    matches y rompe). Registrarlo explícito acá lo arregla para toda
//    la suite sin que cada archivo lo repita.

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import "@testing-library/jest-dom/vitest";

afterEach(() => {
  cleanup();
});
