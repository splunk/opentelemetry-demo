// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { NextPage } from 'next';
import Head from 'next/head';
import { useEffect, useRef } from 'react';
import Layout from '../../components/Layout';
import Recommendations from '../../components/Recommendations';
import * as S from '../../styles/Cart.styled';
import CartDetail from '../../components/Cart/CartDetail';
import EmptyCart from '../../components/Cart/EmptyCart';
import { useCart } from '../../providers/Cart.provider';
import AdProvider from '../../providers/Ad.provider';

const Cart: NextPage = () => {
  const {
    cart: { items },
  } = useCart();

  // ============================================================================
  // DEMO: Synthetic CartPageError for Splunk RUM training
  // ============================================================================
  // This simulates a common race condition bug: trying to access cart item
  // pricing data before the pricing service response is ready.
  //
  // In a real app, this could happen when:
  //   - Component renders before async pricing data loads
  //   - API response is delayed or partially loaded
  //   - Cache miss causes undefined data access
  //
  // This error fires ONCE per browser session to demonstrate how JavaScript
  // errors appear in Splunk RUM with stack traces and workflow attribution.
  // ============================================================================
  const cartErrorSentRef = useRef(false);

  useEffect(() => {
    // Only fire once per session, and only when cart has items
    if (cartErrorSentRef.current || items.length === 0) return;
    if (typeof window === 'undefined' || !(window as any).tracer) return;

    cartErrorSentRef.current = true;

    const tracer = (window as any).tracer;
    const span = tracer.startSpan('CartPageError', {
      attributes: {
        'workflow.name': 'CartPageError',
        'error': true,
        'error.synthetic': true, // Mark as synthetic for filtering if needed
      },
    });

    // Simulate: "Oops! Tried to read pricing before the pricing service responded"
    const error = new Error("Cannot read property 'unitPrice' of undefined - pricing data not yet loaded");
    error.name = 'TypeError';

    // Record on span - Splunk RUM will capture the stack trace
    span.recordException(error);
    span.setStatus({ code: 2, message: error.message });

    console.error('[Demo] CartPageError: Simulated pricing race condition -', error.message);

    span.end();
  }, [items.length]);

  return (
    <AdProvider
      productIds={items.map(({ productId }) => productId)}
      contextKeys={[...new Set(items.flatMap(({ product }) => product.categories))]}
    >
      <Head>
        <title>Otel Demo - Cart</title>
      </Head>
      <Layout>
        <S.Cart>
          {(!!items.length && <CartDetail />) || <EmptyCart />}
          <Recommendations />
        </S.Cart>
      </Layout>
    </AdProvider>
  );
};

export default Cart;
