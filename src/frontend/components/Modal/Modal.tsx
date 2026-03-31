// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from 'react';
import styled from 'styled-components';
import Button from '../Button';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  type?: 'error' | 'warning' | 'info';
}

const Overlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
`;

const ModalContainer = styled.div<{ $type: 'error' | 'warning' | 'info' }>`
  background: white;
  border-radius: 12px;
  padding: 24px;
  max-width: 500px;
  width: 90%;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  border-top: 4px solid ${({ $type }) =>
    $type === 'error' ? '#dc3545' :
    $type === 'warning' ? '#ffc107' :
    '#5262a8'};
`;

const ModalHeader = styled.div<{ $type: 'error' | 'warning' | 'info' }>`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  color: ${({ $type }) =>
    $type === 'error' ? '#dc3545' :
    $type === 'warning' ? '#856404' :
    '#5262a8'};
`;

const ModalTitle = styled.h2`
  margin: 0;
  font-size: 20px;
  font-weight: 700;
`;

const ModalBody = styled.div`
  color: #333;
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 24px;
`;

const ModalFooter = styled.div`
  display: flex;
  justify-content: flex-end;
`;

const CloseButton = styled(Button)`
  height: 44px;
  font-size: 16px;
`;

const Modal = ({ isOpen, onClose, title, children, type = 'info' }: ModalProps) => {
  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getIcon = () => {
    switch (type) {
      case 'error':
        return '❌';
      case 'warning':
        return '⚠️';
      default:
        return 'ℹ️';
    }
  };

  return (
    <Overlay onClick={onClose}>
      <ModalContainer $type={type} onClick={(e) => e.stopPropagation()}>
        {title && (
          <ModalHeader $type={type}>
            <span>{getIcon()}</span>
            <ModalTitle>{title}</ModalTitle>
          </ModalHeader>
        )}
        <ModalBody>{children}</ModalBody>
        <ModalFooter>
          <CloseButton id="modal-close-btn" onClick={onClose}>
            Close
          </CloseButton>
        </ModalFooter>
      </ModalContainer>
    </Overlay>
  );
};

export default Modal;
