/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * URL base de la API. Vacía en desarrollo (el proxy de Vite maneja /api);
   * en Vercel se define con la URL del backend en Render.
   */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
