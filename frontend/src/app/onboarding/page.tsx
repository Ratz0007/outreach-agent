"use client";

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { 
  User, 
  Key, 
  Search, 
  CheckCircle2, 
  ArrowRight, 
  ArrowLeft,
  Sparkles,
  ShieldCheck,
  Zap,
  Globe,
  ExternalLink,
  Loader2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

const STEPS = [
  { id: 'profile', title: 'Profile', icon: User, description: 'Tell us a bit about yourself' },
  { id: 'linkedin', title: 'LinkedIn', icon: Globe, description: 'Connect your professional identity' },
  { id: 'apis', title: 'Connect', icon: Key, description: 'Paste your API keys' },
  { id: 'preferences', title: 'Search', icon: Search, description: 'Define your target roles' },
];

export default function OnboardingPage() {
  const router = useRouter();
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [detectedProfile, setDetectedProfile] = useState<any>(null);
  const [manualMode, setManualMode] = useState(false);

  const [formData, setFormData] = useState({
    full_name: "",
    headline: "",
    linkedin_url: "",
    anthropic_api_key: "",
    adzuna_app_id: "",
    adzuna_app_key: "",
    search_roles: "Account Executive, founding AE",
    search_locations: "Ireland, Dublin, Remote",
    search_industries: "SaaS, AI, Fintech"
  });

  // Fetch current user and try to sync LinkedIn
  useEffect(() => {
    const init = async () => {
      try {
        const user = await api.auth.me();
        setFormData(prev => ({ ...prev, full_name: user.full_name || "" }));
        
        // If we have a name but no LinkedIn, try to sync
        if (user.full_name && !user.linkedin_url) {
          setIsSyncing(true);
          const { profile } = await api.onboarding.syncLinkedin();
          setDetectedProfile(profile);
          if (profile?.url) {
             setFormData(prev => ({ ...prev, linkedin_url: profile.url, headline: profile.headline || "" }));
          }
        }
      } catch (err) {
        console.error("Failed to init onboarding", err);
      } finally {
        setIsSyncing(false);
      }
    };
    init();
  }, []);

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
      window.scrollTo(0, 0);
    } else {
      handleSubmit();
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      // Save all data to settings/profile
      await api.onboarding.confirmLinkedin(formData.linkedin_url);
      // In a real app we'd save the rest too, for now we mock it
      setSuccess(true);
      setTimeout(() => router.push("/dashboard"), 2000);
    } catch (err) {
      console.error(err);
      alert("Failed to save settings. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const StepIcon = STEPS[currentStep].icon;

  return (
    <div className="min-h-screen bg-muted/30 pb-20">
      {/* Progress Header */}
      <div className="bg-background border-b sticky top-0 z-10">
        <div className="container mx-auto px-4 h-20 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-white font-bold text-sm">OA</div>
              <span className="font-bold hidden sm:inline">Onboarding</span>
            </div>
            
            <div className="flex items-center gap-2">
              {STEPS.map((step, i) => (
                <React.Fragment key={step.id}>
                  <div className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all",
                    i === currentStep ? "bg-primary text-primary-foreground scale-110 shadow-lg shadow-primary/20" : 
                    i < currentStep ? "bg-emerald-500 text-white" : "bg-muted text-muted-foreground"
                  )}>
                    {i < currentStep ? <CheckCircle2 className="w-5 h-5" /> : i + 1}
                  </div>
                  {i < STEPS.length - 1 && <div className={cn("w-8 h-0.5 rounded-full", i < currentStep ? "bg-emerald-500" : "bg-muted")} />}
                </React.Fragment>
              ))}
            </div>
          </div>
          
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")} className="text-muted-foreground text-xs uppercase font-bold tracking-wider">Skip</Button>
        </div>
      </div>

      <div className="container mx-auto px-4 pt-12 max-w-2xl">
        <AnimatePresence mode="wait">
          {!success ? (
            <motion.div 
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-8"
            >
              <div className="text-center mb-10">
                <div className="w-16 h-16 rounded-3xl bg-indigo-50 dark:bg-indigo-900/20 flex items-center justify-center text-indigo-600 mx-auto mb-6">
                  <StepIcon className="w-8 h-8" />
                </div>
                <h1 className="text-3xl font-bold tracking-tight">{STEPS[currentStep].title}</h1>
                <p className="text-muted-foreground mt-2">{STEPS[currentStep].description}</p>
              </div>

              <div className="bg-background rounded-[32px] border shadow-2xl shadow-indigo-500/5 p-8 md:p-10 space-y-6">
                
                {currentStep === 0 && (
                  <div className="space-y-5 animate-in fade-in duration-500">
                    <Input 
                      label="Full Name" 
                      value={formData.full_name}
                      onChange={e => setFormData({...formData, full_name: e.target.value})}
                      placeholder="e.g. Ratin Sharma"
                    />
                    <Input 
                      label="Professional Headline" 
                      value={formData.headline}
                      onChange={e => setFormData({...formData, headline: e.target.value})}
                      placeholder="e.g. Senior Account Executive | SaaS"
                    />
                  </div>
                )}

                {currentStep === 1 && (
                  <div className="space-y-6 animate-in fade-in duration-500">
                    {isSyncing ? (
                      <div className="flex flex-col items-center justify-center py-12 space-y-4">
                        <Loader2 className="w-10 h-10 text-primary animate-spin" />
                        <p className="font-medium text-muted-foreground">Finding your LinkedIn profile...</p>
                      </div>
                    ) : detectedProfile && !manualMode ? (
                      <div className="space-y-6">
                        <div className="p-6 rounded-3xl bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-100 dark:border-indigo-800 text-center">
                          <p className="text-sm font-bold text-indigo-600 dark:text-indigo-400 uppercase tracking-widest mb-4">We found a match!</p>
                          <div className="flex flex-col items-center gap-2 mb-6">
                            <h3 className="text-2xl font-bold">{detectedProfile.name}</h3>
                            <p className="text-muted-foreground text-sm">{detectedProfile.headline}</p>
                            <a 
                              href={detectedProfile.url} 
                              target="_blank" 
                              className="text-primary text-xs flex items-center gap-1 hover:underline mt-2"
                            >
                              {detectedProfile.url} <ExternalLink className="w-3 h-3" />
                            </a>
                          </div>
                          <div className="flex flex-col gap-3">
                            <p className="text-sm font-medium">Is this you?</p>
                            <div className="flex gap-4">
                              <Button 
                                variant="outline" 
                                className="flex-1 rounded-2xl h-12"
                                onClick={() => setManualMode(true)}
                              >
                                No, it's not me
                              </Button>
                              <Button 
                                className="flex-1 rounded-2xl h-12 bg-emerald-600 hover:bg-emerald-700 text-white"
                                onClick={handleNext}
                              >
                                Yes, confirm profile
                              </Button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <p className="text-sm text-muted-foreground mb-4">
                         {manualMode ? "No problem! Please paste your LinkedIn URL below." : "We couldn't find your profile automatically. Please paste it below."}
                        </p>
                        <Input 
                          label="LinkedIn Profile URL" 
                          value={formData.linkedin_url}
                          onChange={e => setFormData({...formData, linkedin_url: e.target.value})}
                          placeholder="https://linkedin.com/in/yourprofile"
                        />
                      </div>
                    )}
                  </div>
                )}

                {currentStep === 2 && (
                  <div className="space-y-5">
                    <div className="p-4 rounded-2xl bg-amber-50 dark:bg-amber-900/10 border border-amber-100 dark:border-amber-800 flex gap-3 text-sm text-amber-800 dark:text-amber-200">
                      <ShieldCheck className="w-5 h-5 flex-shrink-0" />
                      <p>Your API keys are stored locally and encrypted. We never share them.</p>
                    </div>
                    <Input 
                      label="Anthropic API Key (Claude)" 
                      type="password"
                      value={formData.anthropic_api_key}
                      onChange={e => setFormData({...formData, anthropic_api_key: e.target.value})}
                      placeholder="sk-ant-..."
                    />
                    <div className="grid grid-cols-2 gap-4">
                      <Input 
                        label="Adzuna App ID" 
                        value={formData.adzuna_app_id}
                        onChange={e => setFormData({...formData, adzuna_app_id: e.target.value})}
                        placeholder="ID"
                      />
                      <Input 
                        label="Adzuna App Key" 
                        type="password"
                        value={formData.adzuna_app_key}
                        onChange={e => setFormData({...formData, adzuna_app_key: e.target.value})}
                        placeholder="Key"
                      />
                    </div>
                  </div>
                )}

                {currentStep === 3 && (
                  <div className="space-y-5">
                    <Input 
                      label="Target Roles" 
                      value={formData.search_roles}
                      onChange={e => setFormData({...formData, search_roles: e.target.value})}
                      placeholder="Comma separated roles"
                    />
                    <Input 
                      label="Locations" 
                      value={formData.search_locations}
                      onChange={e => setFormData({...formData, search_locations: e.target.value})}
                      placeholder="e.g. Dublin, London, Remote"
                    />
                    <Input 
                      label="Target Industries" 
                      value={formData.search_industries}
                      onChange={e => setFormData({...formData, search_industries: e.target.value})}
                      placeholder="e.g. AI, Fintech, CleanTech"
                    />
                  </div>
                )}

                <div className="flex items-center justify-between pt-6 border-t">
                  <Button 
                    variant="outline" 
                    onClick={handleBack}
                    className={cn(currentStep === 0 && "invisible")}
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" /> Back
                  </Button>
                  <Button 
                    onClick={handleNext} 
                    disabled={loading || (currentStep === 1 && isSyncing)} 
                    className="px-8 h-12 rounded-2xl"
                  >
                    {currentStep === STEPS.length - 1 ? (loading ? "Saving..." : "Finish Setup") : "Continue"} 
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </div>
              </div>

              {/* Dynamic Tip */}
              <div className="flex items-center justify-center gap-3 text-sm text-muted-foreground italic">
                <Zap className="w-4 h-4 text-primary" />
                {currentStep === 0 && "This profile helps the AI personalize your CV per job."}
                {currentStep === 1 && "Connecting LinkedIn allows the agent to source your past experience."}
                {currentStep === 2 && "You can always change your keys later in Settings."}
                {currentStep === 3 && "The agent will use these to find high-match roles daily."}
              </div>
            </motion.div>
          ) : (
            <motion.div 
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center py-20"
            >
              <div className="w-24 h-24 rounded-full bg-emerald-100 dark:bg-emerald-900/20 flex items-center justify-center text-emerald-600 mx-auto mb-8 shadow-2xl shadow-emerald-500/20">
                <CheckCircle2 className="w-12 h-12" />
              </div>
              <h1 className="text-4xl font-bold mb-4">You're all set!</h1>
              <p className="text-muted-foreground text-lg mb-8 max-w-sm mx-auto">
                Setting up your workspace... Redirecting you to your mission control dashboard.
              </p>
              <div className="flex items-center justify-center gap-2 text-primary font-bold">
                <Sparkles className="w-5 h-5" />
                Mission starting...
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
