"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { GoogleLoginButton } from '@/components/auth/google-login-button';

export default function RegisterPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
    full_name: ""
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await api.auth.register(formData);
      router.push("/onboarding");
    } catch (err: any) {
      setError(err.message || "Registration failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 px-4 py-20">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <Link href="/" className="inline-flex items-center gap-2 mb-6 group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-500/20 group-hover:scale-110 transition-transform text-lg">
              OA
            </div>
            <span className="font-bold text-2xl tracking-tighter">Outreach Agent</span>
          </Link>
          <h1 className="text-3xl font-bold tracking-tight">Create your account</h1>
          <p className="text-muted-foreground mt-2">Join thousands of job seekers using AI.</p>
        </div>

        <div className="bg-background rounded-[32px] border shadow-2xl shadow-indigo-500/5 p-8 md:p-10">
          {error && (
            <div className="mb-6 p-4 rounded-2xl bg-destructive/10 border border-destructive/20 text-destructive text-sm font-medium animate-in fade-in slide-in-from-top-2">
              {error}
            </div>
          )}

          <div className="space-y-6">
            <GoogleLoginButton />
            
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground font-medium">Or continue with email</span>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <Input 
                label="Full Name" 
                placeholder="e.g. Ratin Sharma"
                required
                value={formData.full_name}
                onChange={(e) => setFormData({...formData, full_name: e.target.value})}
              />
              <Input 
                label="Email Address" 
                type="email" 
                placeholder="you@example.com"
                required
                value={formData.email}
                onChange={(e) => setFormData({...formData, email: e.target.value})}
              />
              <Input 
                label="Username" 
                placeholder="Choose a unique username"
                required
                value={formData.username}
                onChange={(e) => setFormData({...formData, username: e.target.value})}
              />
              <Input 
                label="Password" 
                type="password" 
                placeholder="Min. 6 characters"
                required
                value={formData.password}
                onChange={(e) => setFormData({...formData, password: e.target.value})}
              />

              <Button type="submit" className="w-full h-14 text-base" disabled={loading}>
                {loading ? "Creating Account..." : "Create Account"}
              </Button>
            </form>
          </div>

          <div className="mt-8 pt-8 border-t text-center">
            <p className="text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link href="/login" className="text-primary font-bold hover:underline underline-offset-4">
                Sign In
              </Link>
            </p>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-8 px-6 leading-relaxed">
          By creating an account, you agree to our Terms of Service and Privacy Policy. All API keys are stored securely and encrypted.
        </p>
      </div>
    </div>
  );
}
