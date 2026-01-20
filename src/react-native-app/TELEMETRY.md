# Splunk RUM Telemetry Guide for React Native Mobile App

This document explains how custom events, attributes, and spans are implemented in the Astronomy Shop mobile app using Splunk RUM.

## Overview

The mobile app uses the same telemetry patterns as the web frontend, providing:
- **Global Attributes**: User and deployment context attached to all telemetry
- **Custom Spans**: Track specific workflows like AddToCart, PlaceOrder
- **Error Tracking**: Capture exceptions with full context
- **Session Management**: Deterministic user generation with 30-minute timeout

## Global Attributes

Global attributes are automatically attached to all RUM telemetry and initialized when the app starts.

### Attributes

| Attribute | Type | Description | Example Values |
|-----------|------|-------------|----------------|
| `enduser.id` | string | Unique user identifier | Admin: 34/37/41<br>Member: 1000-6000<br>Guest: 99999 |
| `enduser.role` | string | User role | Admin, Member, Guest |
| `deployment.type` | string | Deployment environment | green, blue, canary |

### User Generation Logic

Users are deterministically generated from a session UUID stored in AsyncStorage:

- **8% Admin users** (IDs: 34, 37, 41)
- **42% Member users** (IDs: 1000-6000)
- **50% Guest users** (ID: 99999)

This ensures the same session ID always generates the same user, allowing consistent tracking across app restarts.

### Session Management

- **Storage**: AsyncStorage (React Native persistent storage)
- **Key**: `@astronomy_shop:session`
- **Timeout**: 30 minutes of inactivity
- **Reset**: Automatic on expiration, or manual via `resetSession()`

### Implementation

Global attributes are configured in `hooks/useSplunkRum.ts`:

```typescript
import { getSplunkGlobalAttributes } from '../utils/UserAttributes';

const globalAttributes = await getSplunkGlobalAttributes();

const rum = SplunkRum.init({
  realm: SPLUNK_RUM_REALM,
  rumAccessToken: SPLUNK_RUM_TOKEN,
  applicationName: SPLUNK_APP_NAME,
  deploymentEnvironment: SPLUNK_RUM_ENV,
  globalAttributes, // User attributes automatically included
});
```

## Custom Spans and Workflows

Custom spans track specific user workflows through the app.

### Creating a Workflow Span

```typescript
import { executeWithWorkflowSpan } from '../utils/TelemetryUtils';

// Automatic span management (recommended)
await executeWithWorkflowSpan('AddToCart',
  {
    'product.id': item.productId,
    'product.quantity': item.quantity
  },
  async () => {
    // Your workflow logic
    await addItemToCart(item);
  }
);
```

### Manual Span Management

```typescript
import { createWorkflowSpan } from '../utils/TelemetryUtils';

const span = await createWorkflowSpan('PlaceOrder', {
  'workflow.name': 'PlaceOrder',
});

try {
  // Your workflow logic
  await placeOrder(order);
} catch (error) {
  span?.recordException(error);
  span?.setStatus({ code: 2, message: error.message });
  throw error;
} finally {
  span?.end();
}
```

## Error Tracking

### Automatic Error Tracking

Errors are automatically captured when using `executeWithWorkflowSpan`:

```typescript
await executeWithWorkflowSpan('LoadProducts', {}, async () => {
  // If this throws, the error is automatically recorded
  const products = await fetchProducts();
});
```

### Synthetic Errors (for testing)

Create synthetic errors for demo/testing purposes:

```typescript
import { createSyntheticError } from '../utils/TelemetryUtils';

createSyntheticError(
  'CartLoadError',
  new Error('Failed to load pricing data'),
  {
    'error.type': 'PricingRaceCondition',
    'cart.itemCount': items.length
  }
);
```

## Custom Events

Add custom events to track specific user interactions:

```typescript
import { addSpanEvent } from '../utils/TelemetryUtils';

addSpanEvent('ProductViewed', {
  'product.id': product.id,
  'product.name': product.name,
  'product.price': product.price
});
```

## Updating Global Attributes

Dynamically update global attributes during the session:

```typescript
import { updateGlobalAttributes } from '../utils/TelemetryUtils';

// Example: User upgrades from Guest to Member
updateGlobalAttributes({
  'enduser.id': '1234',
  'enduser.role': 'Member'
});
```

## Example Usage in Components

### Cart Provider Example

```typescript
import { executeWithWorkflowSpan } from '../utils/TelemetryUtils';

const addItem = async (item: CartItem) => {
  await executeWithWorkflowSpan('AddToCart',
    {
      'product.id': item.productId,
      'product.quantity': item.quantity,
    },
    async () => {
      await addCartMutation.mutateAsync({
        ...item,
        currencyCode: selectedCurrency
      });
    }
  );
};
```

### Product Screen Example

```typescript
import { addSpanEvent } from '../utils/TelemetryUtils';

useEffect(() => {
  if (product) {
    // Track product views
    addSpanEvent('ProductViewed', {
      'product.id': product.id,
      'product.name': product.name,
      'product.category': product.category
    });
  }
}, [product]);
```

## Testing Your Implementation

### View Console Logs

The telemetry utils log all operations to the console:

```
Generated user from session ID: abc-123 -> User ID: 1234 Role: Member
Initializing Splunk RUM with global attributes: { enduser.id: '1234', ... }
Splunk RUM initialized successfully
```

### Test Session Expiration

```typescript
import { resetSession, getSessionId } from '../utils/UserAttributes';

// Force a new session
await resetSession();
const newSessionId = await getSessionId();
console.log('New session:', newSessionId);
```

### Test Custom Spans in Splunk RUM

1. Trigger a workflow (e.g., add item to cart)
2. Open Splunk Observability Cloud
3. Navigate to RUM → Mobile → Sessions
4. Find your session and view spans
5. Verify custom attributes appear on spans

## File Structure

```
src/react-native-app/
├── hooks/
│   └── useSplunkRum.ts          # RUM initialization with global attributes
├── utils/
│   ├── UserAttributes.ts        # Session management and user generation
│   └── TelemetryUtils.ts        # Custom spans, events, and error tracking
└── TELEMETRY.md                 # This documentation
```

## Comparison with Web Frontend

| Feature | Web Frontend | Mobile App |
|---------|-------------|------------|
| Storage | `localStorage` | `AsyncStorage` |
| Global Attributes | `getSplunkGlobalAttributes()` | `getSplunkGlobalAttributes()` |
| Tracer Access | `window.tracer` | `SplunkRum.provider.getTracer()` |
| Span Creation | `tracer.startSpan()` | `tracer.startSpan()` |
| Session Timeout | 30 minutes | 30 minutes |
| User Distribution | 8% Admin, 42% Member, 50% Guest | Same |

## References

- [Splunk RUM React Native SDK](https://github.com/signalfx/splunk-otel-react-native)
- [OpenTelemetry JavaScript SDK](https://opentelemetry.io/docs/instrumentation/js/)
- Frontend implementation: `src/frontend/GLOBAL_ATTRIBUTES.MD`
- Frontend global attributes: `src/frontend/public/global-attributes.js`
