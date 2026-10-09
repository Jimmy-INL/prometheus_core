import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ListOrdered, Clock, GitBranch, Loader2,
  CheckCircle2, XCircle, Circle,
} from "lucide-react";

const STATUS_ICONS = {
  pending: <Circle className="h-4 w-4 text-muted-foreground" />,
  running: <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />,
  completed: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  failed: <XCircle className="h-4 w-4 text-red-500" />,
};

export default function PlanViewer() {
  const [showDetails, setShowDetails] = useState(false);

  const plan = props.plan || {};
  const steps = plan.steps || [];
  const stepStatuses = props.stepStatuses || {};
  const workflowType = plan.workflow_type || "sequential";
  const estimatedDuration = plan.estimated_duration_seconds;
  const intent = plan.intent || "";
  const skills = plan.skills || [];
  const selectionSource = plan.selection_source;
  const workflowId = plan.workflow_id;

  return (
    <Card className="w-full border-2 border-blue-200 bg-blue-50/30">
      <CardHeader className="pb-2">
        <CardTitle className="text-md font-medium flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ListOrdered className="h-4 w-4" />
            <span>Execution Plan</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs capitalize">
              <GitBranch className="h-3 w-3 mr-1" />
              {workflowType}
            </Badge>
            {estimatedDuration && (
              <Badge variant="secondary" className="text-xs">
                <Clock className="h-3 w-3 mr-1" />
                ~{estimatedDuration}s
              </Badge>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {intent && (
          <p className="text-sm text-muted-foreground mb-3 italic">{intent}</p>
        )}
        <div className="flex flex-col gap-1">
          {steps.map((step, index) => {
            const status = stepStatuses[index] || "pending";
            const icon = STATUS_ICONS[status] || STATUS_ICONS.pending;
            const stepText = typeof step === "string"
              ? step
              : `${step.name || step.agent || `Step ${index + 1}`}: ${step.description || step.prompt || ""}`;

            return (
              <div key={index} className="flex items-start gap-2 py-1">
                <div className="mt-0.5">{icon}</div>
                <span className="text-sm">{index + 1}. {stepText}</span>
              </div>
            );
          })}
        </div>
        {(workflowId || selectionSource || skills.length > 0) && (
          <div className="mt-3 pt-2 border-t">
            <button
              className="text-xs text-muted-foreground underline"
              onClick={() => setShowDetails(!showDetails)}
            >
              {showDetails ? "Hide details" : "Show details"}
            </button>
            {showDetails && (
              <div className="mt-2 text-xs text-muted-foreground space-y-1">
                {workflowId && <p>Workflow: <code>{workflowId}</code></p>}
                {selectionSource && <p>Source: {selectionSource}</p>}
                {skills.length > 0 && <p>Skills: {skills.join(" → ")}</p>}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
