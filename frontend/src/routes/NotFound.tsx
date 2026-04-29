import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/empty/EmptyState";

export function NotFound(): JSX.Element {
  return (
    <div className="space-y-4">
      <EmptyState
        title="Route not found"
        message="That URL is not part of Ultimate Trader's V1 surfaces."
        action={
          <Link to="/">
            <Button variant="secondary" size="sm">
              Back to Dashboard
            </Button>
          </Link>
        }
      />
    </div>
  );
}
