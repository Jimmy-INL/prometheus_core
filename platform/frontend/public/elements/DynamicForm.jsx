// This file is part of Prometheus
// https://inl.gov/super-intelligence/prometheus/
//
// Copyright 2026 Battelle Energy Alliance, LLC
// All rights reserved, see NOTICE.txt for full restrictions
// https://github.com/idaholab/prometheus_core/blob/main/NOTICE.txt
//
// Licensed under the MIT License, please see LICENSE for details
// https://github.com/idaholab/prometheus_core/blob/main/LICENSE
//
// SPDX-License-Identifier: MIT

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import React, { useEffect, useMemo, useState } from 'react';

export default function DynamicForm() {
  const [timeLeft, setTimeLeft] = useState(props.timeout || 30);
  const [values, setValues] = useState(() => {
    const init = {};
    (props.fields || []).forEach((f) => {
      init[f.id] = f.value || '';
    });
    return init;
  });

  const [errors, setErrors] = useState({});

  const allValid = useMemo(() => {
    if (!props.fields) return true;
    return props.fields.every((f) => {
      if (!f.required) return true;
      const val = values[f.id];
      if (f.input_type === 'checkbox') return true; // checkboxes are optional by default
      return val !== undefined && val !== '';
    });
  }, [props.fields, values]);

  useEffect(() => {
    const interval = setInterval(() => {
      setTimeLeft((t) => (t > 0 ? t - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleChange = (id, val) => {
    setValues((v) => ({ ...v, [id]: val }));
    // Clear error when user changes value
    if (errors[id]) {
      setErrors((e) => ({ ...e, [id]: null }));
    }
  };

  const validateAndSubmit = () => {
    const newErrors = {};
    props.fields.forEach((field) => {
      if (field.required && field.input_type !== 'checkbox') {
        const val = values[field.id];
        if (!val || val === '') {
          newErrors[field.id] = `${field.label} is required`;
        }
      }
    });
    
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    
    submitElement(values);
  };

  const renderField = (field) => {
    const value = values[field.id];
    const hasError = errors[field.id];
    
    switch (field.input_type) {
      case 'textarea':
        return (
          <Textarea
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            rows={field.rows || 4}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      case 'select':
        return (
          <Select value={value} onValueChange={(val) => handleChange(field.id, val)}>
            <SelectTrigger id={field.id} className={hasError ? 'border-red-500' : ''}>
              <SelectValue placeholder={`Select ${field.label}`} />
            </SelectTrigger>
            <SelectContent>
              {(field.options || []).map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      
      case 'checkbox':
        return (
          <div className="flex items-center space-x-2">
            <Checkbox
              id={field.id}
              checked={value === true || value === 'true'}
              onCheckedChange={(checked) => handleChange(field.id, checked)}
              disabled={field.disabled || false}
            />
            <label
              htmlFor={field.id}
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              {field.checkboxLabel || field.label}
            </label>
          </div>
        );
      
      case 'number':
        return (
          <Input
            type="number"
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            min={field.min}
            max={field.max}
            step={field.step}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      case 'email':
        return (
          <Input
            type="email"
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      case 'password':
        return (
          <Input
            type="password"
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      case 'date':
        return (
          <Input
            type="date"
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      case 'datetime':
        return (
          <Input
            type="datetime-local"
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
      
      default: // text
        return (
          <Input
            id={field.id}
            value={value}
            onChange={(e) => handleChange(field.id, e.target.value)}
            placeholder={field.placeholder || ''}
            disabled={field.disabled || false}
            className={hasError ? 'border-red-500' : ''}
          />
        );
    }
  };

  return (
    <Card id="dynamic-form" className="mt-4 w-full max-w-3xl">
      <CardHeader>
        <CardTitle>{props.title || 'Form'}</CardTitle>
        <CardDescription>
          {props.description || 'Please fill out the form below.'}
          {props.timeout > 0 && props.timeout < 300 && ` ${timeLeft}s left`}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4">
        {(props.fields || []).map((field) => (
          <div key={field.id} className="flex flex-col gap-2">
            {field.input_type !== 'checkbox' && (
              <Label htmlFor={field.id}>
                {field.label}
                {field.required && <span className="text-red-500 ml-1">*</span>}
              </Label>
            )}
            {renderField(field)}
            {field.help && (
              <p className="text-sm text-muted-foreground">{field.help}</p>
            )}
            {errors[field.id] && (
              <p className="text-sm text-red-500">{errors[field.id]}</p>
            )}
          </div>
        ))}
      </CardContent>
      <CardFooter className="flex justify-end gap-2">
        <Button
          id="form-cancel"
          variant="outline"
          onClick={() => cancelElement()}
        >
          {props.cancelLabel || 'Cancel'}
        </Button>
        <Button
          id="form-submit"
          disabled={!allValid}
          onClick={validateAndSubmit}
        >
          {props.submitLabel || 'Submit'}
        </Button>
      </CardFooter>
    </Card>
  );
}