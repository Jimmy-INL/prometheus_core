import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Brain, ChevronDown, ChevronUp, Search, BookOpen } from "lucide-react";

export default function MemoryCards() {
  const [expanded, setExpanded] = useState(false);

  const factoids = props.factoids || [];
  const retrieved = props.numRetrieved || 0;
  const stored = props.numStored || 0;
  const title = props.title || "Memory Context";

  if (factoids.length === 0 && retrieved === 0 && stored === 0) {
    return null;
  }

  return (
    <Card className="w-full border border-primary/20 bg-primary/5">
      <CardHeader className="pb-2 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            <span>{title}</span>
          </div>
          <div className="flex items-center gap-2">
            {retrieved > 0 && (
              <Badge variant="secondary" className="text-xs">
                <Search className="h-3 w-3 mr-1" />
                {retrieved} recalled
              </Badge>
            )}
            {stored > 0 && (
              <Badge variant="default" className="text-xs">
                <BookOpen className="h-3 w-3 mr-1" />
                {stored} learned
              </Badge>
            )}
            {factoids.length > 0 && (
              expanded
                ? <ChevronUp className="h-4 w-4" />
                : <ChevronDown className="h-4 w-4" />
            )}
          </div>
        </CardTitle>
      </CardHeader>
      {expanded && factoids.length > 0 && (
        <CardContent className="pt-0">
          <div className="flex flex-col gap-2">
            {factoids.map((factoid, index) => (
              <div key={index} className="rounded-md border p-2 text-sm bg-background">
                <div className="flex items-center gap-2 mb-1">
                  {factoid.material_id && (
                    <Badge variant="outline" className="text-xs">{factoid.material_id}</Badge>
                  )}
                  {factoid.analysis_type && (
                    <Badge variant="outline" className="text-xs">{factoid.analysis_type}</Badge>
                  )}
                  {factoid.factoid_type && (
                    <Badge variant="secondary" className="text-xs">{factoid.factoid_type}</Badge>
                  )}
                  {factoid.confidence != null && (
                    <span className="text-xs text-muted-foreground ml-auto">
                      {Math.round(factoid.confidence * 100)}% confidence
                    </span>
                  )}
                </div>
                <p className="text-sm text-foreground">{factoid.content}</p>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
