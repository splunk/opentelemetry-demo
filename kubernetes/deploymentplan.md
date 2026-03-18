flowchart TD

    A[GitHub Action: Promote<br/>Select Version X.X.X]

    A --> B[Copy Standard Manifests]

    B --> C1[splunk_astronomy-shop-demo-X.X.X.yaml]
    B --> C2[splunk_astronomy-shop-demo-X.X.X-values.yaml]

    C1 --> D1[o11y-field-demos<br/>splunk-astronomy-shop/]
    C2 --> D1

    D1 --> E1[Overwrite<br/>splunk_astronomy-shop-latest.yaml]
    D1 --> E2[Overwrite<br/>splunk-astronomy-values-latest.yaml]


    A --> F[Copy DIAB Manifests]

    F --> G1[splunk_astronomy-shop-demo-X.X.X-diab.yaml]
    F --> G2[splunk_astronomy-shop-demo-X.X.X-values-diab.yaml]

    G1 --> H1[o11y-field-demos<br/>demo-in-a-box/v3/deployments]
    G2 --> H2[o11y-field-demos<br/>demo-in-a-box/v3/opentelemetry-collector]

    H1 --> I1[Overwrite<br/>splunk_astronomy-shop-latest.yaml]
    H2 --> I2[Overwrite<br/>splunk-astronomy-values-latest.yaml]