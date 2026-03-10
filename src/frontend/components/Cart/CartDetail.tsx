// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { useRouter } from 'next/router';
import { useCallback, useState } from 'react';
import CartItems from '../CartItems';
import CheckoutForm from '../CheckoutForm';
import { IFormData } from '../CheckoutForm/CheckoutForm';
import SessionGateway from '../../gateways/Session.gateway';
import { useCart } from '../../providers/Cart.provider';
import { useCurrency } from '../../providers/Currency.provider';
import * as S from '../../styles/Cart.styled';

const { userId } = SessionGateway.getSession();

const CartDetail = () => {
  const {
    cart: { items },
    emptyCart,
    placeOrder,
  } = useCart();
  const { selectedCurrency } = useCurrency();
  const { push } = useRouter();
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  const onPlaceOrder = useCallback(
    async ({
      email,
      state,
      streetAddress,
      country,
      city,
      zipCode,
      creditCardCvv,
      creditCardExpirationMonth,
      creditCardExpirationYear,
      creditCardNumber,
    }: IFormData) => {
      try {
        setCheckoutError(null);

        const order = await placeOrder({
          userId,
          email,
          address: {
            streetAddress,
            state,
            country,
            city,
            zipCode,
          },
          userCurrency: selectedCurrency,
          creditCard: {
            creditCardCvv,
            creditCardExpirationMonth,
            creditCardExpirationYear,
            creditCardNumber,
          },
        });

        // Check if the order response contains an error (backend returned error as 200)
        if ((order as any).error) {
          const errorMessage = (order as any).error;
          setCheckoutError(errorMessage);
          console.error('Checkout failed:', errorMessage);

          // Determine if this is a payment failure specifically
          const isPaymentFailure = errorMessage.toLowerCase().includes('payment') ||
                                   errorMessage.toLowerCase().includes('charge') ||
                                   errorMessage.toLowerCase().includes('card') ||
                                   errorMessage.toLowerCase().includes('token');

          // Create RUM custom workflow event for payment/checkout errors
          if (typeof window !== 'undefined' && (window as any).tracer) {
            const tracer = (window as any).tracer;
            const workflowName = isPaymentFailure ? 'PaymentFailure' : 'CheckoutError';

            const span = tracer.startSpan(workflowName, {
              attributes: {
                'workflow.name': workflowName,
                'error': true,
                'error.type': isPaymentFailure ? 'payment_failure' : 'checkout_failed',
                'error.message': errorMessage,
                'error.category': isPaymentFailure ? 'payment' : 'checkout',
                'user.id': userId,
                'cart.items_count': items.length,
                'checkout.stage': 'place_order',
              },
            });

            // Add custom event with detailed error context
            span.addEvent(isPaymentFailure ? 'payment_processing_failed' : 'checkout_failed', {
              'error.source': 'backend_response',
              'error.details': errorMessage,
              'payment.failed': isPaymentFailure,
              'cart.had_items': items.length > 0,
            });

            span.end();
          }
          return; // Don't navigate to confirmation page
        }

        push({
          pathname: `/order/confirmation/${order.orderId}`,
          query: { order: JSON.stringify(order) },
        });
      } catch (error: any) {
        // Display error message to user
        const errorMessage = error?.message || 'Failed to place order. Please try again.';
        setCheckoutError(errorMessage);
        console.error('Checkout error:', error);

        // Create RUM custom event for checkout errors
        if (typeof window !== 'undefined' && (window as any).tracer) {
          const tracer = (window as any).tracer;
          const isEmptyCartError = errorMessage.toLowerCase().includes('empty cart');

          const span = tracer.startSpan(isEmptyCartError ? 'EmptyCartCheckoutAttempt' : 'CheckoutError', {
            attributes: {
              'workflow.name': isEmptyCartError ? 'EmptyCartCheckoutAttempt' : 'CheckoutError',
              'error': true,
              'error.type': isEmptyCartError ? 'empty_cart' : 'checkout_failed',
              'error.message': errorMessage,
              'user.id': userId,
              'cart.items_count': items.length,
            },
          });

          // Add event to the span
          span.addEvent(isEmptyCartError ? 'empty_cart_checkout_blocked' : 'checkout_failed', {
            'checkout.error': errorMessage,
            'cart.was_empty': isEmptyCartError,
          });

          span.end();
        }
      }
    },
    [placeOrder, push, selectedCurrency, items.length]
  );

  return (
    <S.Container>
      <div>
        <S.Header>
          <S.CarTitle>Shopping Cart</S.CarTitle>
          <S.EmptyCartButton id="btn-empty-cart" onClick={emptyCart} $type="link">
            Empty Cart
          </S.EmptyCartButton>
        </S.Header>
        <CartItems productList={items} />
      </div>
      <div>
        {checkoutError && (
          <div style={{
            backgroundColor: '#fee',
            border: '1px solid #f88',
            borderRadius: '4px',
            padding: '12px 16px',
            marginBottom: '16px',
            color: '#c00',
            fontSize: '14px'
          }}>
            <strong>Checkout Error:</strong> {checkoutError}
          </div>
        )}
        <CheckoutForm onSubmit={onPlaceOrder} />
      </div>
    </S.Container>
  );
};

export default CartDetail;
