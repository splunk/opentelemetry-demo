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
          SPLUNK_RUM_REALM: '${process.env.SPLUNK_RUM_REALM}'
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

//   render() {
//     return (
//       <Html>
//         <Head>
//           <link rel="preconnect" href="https://fonts.googleapis.com" />
//           <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
//           <link
//             href="https://fonts.googleapis.com/css2?family=Open+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,300;1,400;1,500;1,600;1,700;1,800&display=swap"
//             rel="stylesheet"
//           />
//         </Head>
//         <body>
//           <Main />
//           <script dangerouslySetInnerHTML={{ __html: this.props.envString }}></script>
//           <NextScript />
//         </body>
//       </Html>
//     );
//   }

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
          {/* eslint-disable @next/next/no-sync-scripts */}
          {/* Inject window.ENV first */}
          <script dangerouslySetInnerHTML={{ __html: this.props.envString }}></script>
          {/* Load Splunk scripts nextt */}
          <script src="https://cdn.signalfx.com/o11y-gdi-rum/latest/splunk-otel-web.js"></script>
          <script src="https://cdn.signalfx.com/o11y-gdi-rum/latest/splunk-otel-web-session-recorder.js"></script>

          {/* Inline Splunk RUM initialization directly in raw HTML head */}

          <script dangerouslySetInnerHTML={{
            __html: `
              (function initializeSplunkRUM() {
                const rumAccessToken = window.ENV.SPLUNK_RUM_TOKEN;
                const applicationName = window.ENV.SPLUNK_APP_NAME;
                const deploymentEnvironment = window.ENV.SPLUNK_ENV;
                const realm = window.ENV.SPLUNK_RUM_REALM;

                // console.log("Splunk ENV values:", {
                //   rumAccessToken,
                //   applicationName,
                //   deploymentEnvironment,
                //   realm,
                //   fullWindowEnv: window.ENV
                // });

                if (typeof SplunkRum !== 'undefined') {
                  SplunkRum.init({
                    realm: realm,
                    rumAccessToken: rumAccessToken,
                    applicationName: applicationName,
                    deploymentEnvironment: deploymentEnvironment,
                    version: '2.0.5',
                    globalAttributes: {
                      'enduser.id': '5108',
                      'enduser.role': 'Member',
                      'deployment.type': 'pink'
                    },
                    environment: ''
                  });

                  if (typeof SplunkSessionRecorder !== 'undefined') {
                    SplunkSessionRecorder.init({
                      realm: realm,
                      rumAccessToken: rumAccessToken
                    });
                  }
                } else {
                  setTimeout(initializeSplunkRUM, 100);
                }
              })();
            `
          }} />
        </Head>
        <body>
          <Main />
          <script dangerouslySetInnerHTML={{ __html: this.props.envString }}></script>
          <NextScript />
        </body>
      </Html>
    );
  }
}