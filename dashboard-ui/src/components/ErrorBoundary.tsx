import React, { Component, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card card-pad flex flex-col items-center justify-center p-12 text-center">
          <div className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-red-500/10 text-red-500">
            <AlertTriangle className="h-8 w-8" />
          </div>
          <h2 className="mb-2 text-lg font-bold text-heading">Algo salió mal</h2>
          <p className="text-muted">
            Ocurrió un error al cargar esta vista. Puedes intentar navegar a otra pestaña.
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}
