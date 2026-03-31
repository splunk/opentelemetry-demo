// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { NextPage } from 'next';
import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect } from 'react';
import Ad from '../../../../components/Ad';
import Button from '../../../../components/Button';
import CheckoutItem from '../../../../components/CheckoutItem';
import Layout from '../../../../components/Layout';
import Recommendations from '../../../../components/Recommendations';
import AdProvider from '../../../../providers/Ad.provider';
import * as S from '../../../../styles/Checkout.styled';
import { IProductCheckout } from '../../../../types/Cart';

const Checkout: NextPage = () => {
  const { query } = useRouter();
  const orderData = JSON.parse((query.order || '{}') as string);
  const hasError = !!(orderData as any).error;
  const { items = [], shippingAddress, orderId } = orderData as IProductCheckout;

  // Create a custom span for order confirmation or error page view
  useEffect(() => {
    if (typeof window !== 'undefined' && typeof (window as any).tracer !== 'undefined') {
      const tracer = (window as any).tracer;

      if (hasError) {
        // Create RUM custom workflow event for error page view
        const span = tracer.startSpan('OrderConfirmationError', {
          attributes: {
            'workflow.name': 'OrderConfirmationError',
            'error': true,
            'error.type': 'order_confirmation_with_error',
            'error.category': 'order_processing',
            'page.type': 'confirmation',
            'page.state': 'error',
          },
        });

        span.addEvent('error_page_viewed', {
          'error.reached_confirmation': true,
          'error.should_not_happen': true,
        });

        console.log('Order confirmation error page viewed - this should not happen with proper error handling');
        span.end();
      } else if (orderId) {
        // Success case - order confirmed
        const span = tracer.startSpan('order.confirmed', {
          attributes: {
            'workflow.name': 'order.confirmed',
            'order.id': orderId,
            'order.items_count': items.length,
            'order.total_items': items.reduce((sum, item) => sum + item.item.quantity, 0),
            'page.type': 'confirmation',
            'page.state': 'success',
          },
        });

        span.addEvent('order_confirmation_viewed', {
          'order.id': orderId,
          'order.items': items.length,
        });

        console.log('Order confirmation span created:', {
          orderId,
          itemsCount: items.length,
          totalItems: items.reduce((sum, item) => sum + item.item.quantity, 0),
        });

        span.end();
      }
    }
  }, [orderId, items, hasError]);

  return (
    <AdProvider
      productIds={items.map(({ item }) => item?.productId || '')}
      contextKeys={[...new Set(items.flatMap(({ item }) => item.product.categories))]}
    >
      <Head>
        <title>Otel Demo - Order {hasError ? 'Error' : 'Confirmation'}</title>
      </Head>
      <Layout>
        <S.Checkout>
          <S.Container>
            {hasError ? (
              <>
                <S.Title>Oh Dear, there seems to be a problem with your order.</S.Title>
                <S.Subtitle>
                  Please contact a sales representative at{' '}
                  <span style={{ fontWeight: 'bold', whiteSpace: 'nowrap' }}>1-800-ASTRONOMY</span>
                  {' '}(1-800-278-766-669)
                </S.Subtitle>
                <div style={{
                  backgroundColor: '#fff3cd',
                  border: '1px solid #ffc107',
                  borderRadius: '8px',
                  padding: '16px 20px',
                  marginTop: '24px',
                  marginBottom: '24px',
                  color: '#856404',
                  fontSize: '14px'
                }}>
                  <strong>Note:</strong> This is a demonstration phone number and is not in service.
                </div>
              </>
            ) : (
              <>
                <S.Title>Your order is complete!</S.Title>
                <S.Subtitle>We&apos;ve sent you a confirmation email.</S.Subtitle>
              </>
            )}

            {!hasError && (
              <S.ItemList>
                {items.map(checkoutItem => (
                  <CheckoutItem
                    key={checkoutItem.item.productId}
                    checkoutItem={checkoutItem}
                    address={shippingAddress}
                  />
                ))}
              </S.ItemList>
            )}

            <S.ButtonContainer>
              <Link href="/">
                <Button id="btn-order-confirmation-continue-shopping" type="submit">Continue Shopping</Button>
              </Link>
            </S.ButtonContainer>
          </S.Container>
          <Recommendations />
        </S.Checkout>
        <Ad />
      </Layout>
    </AdProvider>
  );
};

export default Checkout;
