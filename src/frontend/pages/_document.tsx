// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import Document, { DocumentContext, Html, Head, Main, NextScript } from 'next/document';
import { ServerStyleSheet } from 'styled-components';
import {context, propagation} from "@opentelemetry/api";

const { ENV_PLATFORM, WEB_OTEL_SERVICE_NAME, PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, OTEL_COLLECTOR_HOST } = process.env;

export default class MyDocument extends Document<{ envString: string }> {
  static async getInitialProps(ctx: DocumentContext) {
    const sheet = new ServerStyleSheet();
    const originalRenderPage = ctx.renderPage;

    try {
      ctx.renderPage = () =>
        originalRenderPage({
          enhanceApp: App => props => sheet.collectStyles(<App {...props} />),
        });

      const initialProps = await Document.getInitialProps(ctx);
      const baggage = propagation.getBaggage(context.active());
      const isSyntheticRequest = baggage?.getEntry('synthetic_request')?.value === 'true';

      const otlpTracesEndpoint = isSyntheticRequest
          ? `http://${OTEL_COLLECTOR_HOST}:4318/v1/traces`
          : PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT;

      const envString = `
        window.ENV = {
          NEXT_PUBLIC_PLATFORM: '${ENV_PLATFORM}',
          NEXT_PUBLIC_OTEL_SERVICE_NAME: '${WEB_OTEL_SERVICE_NAME}',
          NEXT_PUBLIC_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: '${otlpTracesEndpoint}',
          IS_SYNTHETIC_REQUEST: '${isSyntheticRequest}',
          SPLUNK_RUM_TOKEN: '${process.env.SPLUNK_RUM_TOKEN}',
          SPLUNK_APP_NAME: '${process.env.SPLUNK_APP_NAME}',
          SPLUNK_ENV: '${process.env.SPLUNK_RUM_ENV}',
          SPLUNK_RUM_REALM: '${process.env.SPLUNK_RUM_REALM}',
          DEPLOYMENT_TYPE: '${process.env.DEPLOYMENT_TYPE || 'green'}'
        };`;
      return {
        ...initialProps,
        styles: [initialProps.styles, sheet.getStyleElement()],
        envString,
      };
    } finally {
      sheet.seal();
    }
  }

  render() {
    return (
      <Html>
        <Head>
          <link rel="preconnect" href="https://fonts.googleapis.com" />
          <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
          <link
            href="https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,300;1,400;1,500;1,600;1,700;1,800&display=swap"
            rel="stylesheet"
          />
          {/* Inject window.ENV first */}
          <script
              crossOrigin="anonymous"
              dangerouslySetInnerHTML={{ __html: this.props.envString }}>
          </script>
          {/* Load user attributes generator - must load before RUM initialization */}
          <script src="/global-attributes.js"></script>
          <script
              src="https://cdn.signalfx.com/o11y-gdi-rum/next/splunk-otel-web.js"
              crossOrigin="anonymous"
          />
          <script
              id="splunk-rum-init"
              dangerouslySetInnerHTML={{
                __html: `
                  SplunkRum.init({
                    realm: window.ENV.SPLUNK_RUM_REALM,
                    rumAccessToken: window.ENV.SPLUNK_RUM_TOKEN,
                    applicationName: window.ENV.SPLUNK_APP_NAME,
                    deploymentEnvironment: window.ENV.SPLUNK_ENV,
                    globalAttributes: getSplunkGlobalAttributes(),
                    version: '2.0.5',
                    // Digital Experience Analytics configuration
                    user: {
                      trackingMode: 'anonymousTracking'
                    },
                    privacy: {
                      "maskAllText": false
                    },
                    instrumentations: {
                      "frustrationSignals": {
                        "rageClick": true
                      }
                    },
                    _experimental_dataAttributesToCapture: [
                      "data-cy",
                    ],
                    _experimental_spaMetrics: true
                  });
                  
                  // Initialize tracer for custom spans and expose globally
                  const tracer = SplunkRum.provider.getTracer('appModuleLoader');
                  window.tracer = tracer; // Make tracer available globally for custom spans
                `,
              }}
          />
          <script
              src="https://cdn.signalfx.com/o11y-gdi-rum/next/splunk-otel-web-session-recorder.js"
              crossOrigin="anonymous"
          />
          <script
              id="splunk-session-recorder-init"
              dangerouslySetInnerHTML={{
                __html: `
                    SplunkSessionRecorder.init({
                        realm: window.ENV.SPLUNK_RUM_REALM,
                        rumAccessToken: window.ENV.SPLUNK_RUM_TOKEN,
                        maskAllText: false
                    });
                `,
              }}
          />
        </Head>
        <body>
          <Main />
          <NextScript />
        </body>
      </Html>
    );
  }
}