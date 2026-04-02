"use client";

import React, { useState, useEffect } from 'react';
import { 
  Zap, 
  Target, 
  TrendingUp, 
  Briefcase, 
  Users, 
  Send, 
  ArrowUpRight,
  Plus,
  Search,
  Sparkles,
  ChevronRight,
  Clock,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Sidebar } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/top-bar';
import { motion } from 'framer-motion';

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.dashboard.stats().then(setStats).finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex h-screen bg-muted/30">
      <Sidebar />
      <div className="flex-1 pl-20 transition-all duration-300">
        <TopBar />
        <div className="p-8 flex items-center justify-center h-[calc(100vh-80px)]">
           <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" />
              <p className="font-bold text-muted-foreground animate-pulse">Initializing Mission Control...</p>
           </div>
        </div>
      </div>
    </div>
  );

  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 }
  };

  return (
    <div className="flex min-h-screen bg-muted/30">
      <Sidebar />
      <main className="flex-1 pl-20 transition-all duration-300">
        <TopBar />
        
        <div className="p-8 max-w-7xl mx-auto">
          {/* Header */}
          <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
            <div>
              <h1 className="text-3xl font-bold tracking-tight mb-2">Mission Control</h1>
              <p className="text-muted-foreground">Your AI Career Coach is currently active. 4 actions recommended.</p>
            </div>
            <div className="flex items-center gap-3">
               <Button variant="outline" className="rounded-2xl h-12">
                  <Plus className="w-4 h-4 mr-2" /> Add Job
               </Button>
               <Button className="rounded-2xl h-12">
                  <Zap className="w-4 h-4 mr-2" /> Source Jobs
               </Button>
            </div>
          </header>

          <motion.div 
            variants={container}
            initial="hidden"
            animate="show"
            className="grid grid-cols-1 md:grid-cols-12 gap-6"
          >
            {/* KPI Row */}
            <motion.div variants={item} className="md:col-span-3 card bg-background border rounded-[32px] p-6 shadow-sm flex flex-col justify-between group hover:shadow-xl hover:shadow-indigo-500/5 transition-all">
               <div className="flex justify-between items-start">
                  <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-900/20 flex items-center justify-center text-indigo-600 group-hover:scale-110 transition-transform">
                     <Target className="w-6 h-6" />
                  </div>
                  <div className="text-xs font-bold text-emerald-500 flex items-center bg-emerald-50 dark:bg-emerald-900/20 px-2 py-1 rounded-full">+12%</div>
               </div>
               <div className="mt-6">
                  <p className="text-sm font-medium text-muted-foreground uppercase tracking-widest leading-none mb-2">Target Jobs</p>
                  <p className="text-4xl font-extrabold tracking-tight tabular-nums">{stats?.total_jobs || 0}</p>
               </div>
            </motion.div>

            <motion.div variants={item} className="md:col-span-3 card bg-background border rounded-[32px] p-6 shadow-sm flex flex-col justify-between group hover:shadow-xl hover:shadow-purple-500/5 transition-all">
               <div className="flex justify-between items-start">
                  <div className="w-12 h-12 rounded-2xl bg-purple-50 dark:bg-purple-900/20 flex items-center justify-center text-purple-600 group-hover:scale-110 transition-transform">
                     <Users className="w-6 h-6" />
                  </div>
                  <div className="text-xs font-bold text-purple-500 flex items-center bg-purple-50 dark:bg-purple-900/20 px-2 py-1 rounded-full">Active</div>
               </div>
               <div className="mt-6">
                  <p className="text-sm font-medium text-muted-foreground uppercase tracking-widest leading-none mb-2">Total Contacts</p>
                  <p className="text-4xl font-extrabold tracking-tight tabular-nums">{stats?.total_contacts || 0}</p>
               </div>
            </motion.div>

            <motion.div variants={item} className="md:col-span-6 card bg-gradient-to-br from-indigo-500 to-purple-600 rounded-[32px] p-8 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden group">
               <div className="relative z-10 flex flex-col justify-between h-full">
                  <div className="flex justify-between items-start">
                     <div className="w-12 h-12 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center">
                        <TrendingUp className="w-6 h-6" />
                     </div>
                     <p className="text-sm font-bold bg-white/20 backdrop-blur-md px-3 py-1 rounded-full">Week 4 Progress</p>
                  </div>
                  <div className="mt-4">
                     <p className="text-lg font-medium opacity-80 mb-2">Success Rate</p>
                     <p className="text-5xl font-black mb-4">24.5%</p>
                     <div className="w-full h-3 bg-white/20 rounded-full overflow-hidden">
                        <div className="h-full bg-white w-3/4 rounded-full" />
                     </div>
                  </div>
               </div>
               <div className="absolute -right-8 -bottom-8 w-48 h-48 bg-white/10 rounded-full blur-3xl" />
            </motion.div>

            {/* Main Action Area */}
            <motion.div variants={item} className="md:col-span-8 space-y-6">
               <div className="card bg-background border rounded-[40px] p-8 shadow-sm">
                  <div className="flex items-center justify-between mb-8">
                     <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
                           <Zap className="w-5 h-5" />
                        </div>
                        <h2 className="text-xl font-bold">Action Queue</h2>
                     </div>
                     <Button variant="ghost" size="sm" className="font-bold underline decoration-primary/30 underline-offset-4">Review All</Button>
                  </div>
                  
                  <div className="space-y-4">
                     {stats?.priority_queue?.length > 0 ? (
                       stats.priority_queue.map((action: any, i: number) => (
                        <div key={i} className="flex items-center justify-between p-4 rounded-3xl bg-muted/30 border border-muted hover:bg-muted/50 transition-all cursor-pointer group">
                           <div className="flex items-center gap-4">
                              <div className={cn(
                                "w-3 h-3 rounded-full",
                                action.urgency === 'urgent' ? "bg-destructive animate-pulse" : 
                                action.urgency === 'warning' ? "bg-amber-500" : "bg-indigo-500"
                              )} />
                              <div>
                                 <p className="font-bold text-sm">{action.title}</p>
                                 <p className="text-xs text-muted-foreground">{action.desc}</p>
                              </div>
                           </div>
                           <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                        </div>
                       ))
                     ) : (
                       <div className="py-12 text-center">
                          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-4" />
                          <p className="font-bold">Mission Cleared</p>
                          <p className="text-sm text-muted-foreground">No pending items in your queue.</p>
                       </div>
                     )}
                  </div>
               </div>

               <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="card bg-background border rounded-[32px] p-6 shadow-sm">
                     <div className="flex items-center gap-3 mb-6">
                         <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600">
                           <Clock className="w-4 h-4" />
                         </div>
                         <h3 className="font-bold">Recent Events</h3>
                     </div>
                     <div className="space-y-6">
                        {stats?.recent_activity?.map((act: any, i: number) => (
                          <div key={i} className="flex gap-4">
                             <div className="w-[2px] h-10 bg-muted relative">
                                <div className="absolute top-0 -left-1 w-2 h-2 rounded-full bg-primary" />
                             </div>
                             <div>
                                <p className="text-sm font-bold">{act.title}</p>
                                <p className="text-xs text-muted-foreground">{act.time}</p>
                             </div>
                          </div>
                        ))}
                     </div>
                  </div>
                  
                  <div className="card bg-background border rounded-[32px] p-6 shadow-sm relative overflow-hidden">
                     <div className="relative z-10">
                        <div className="flex items-center gap-3 mb-6">
                            <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-600">
                              <Sparkles className="w-4 h-4" />
                            </div>
                            <h3 className="font-bold">Agent Status</h3>
                        </div>
                        <div className="space-y-4">
                           <div className="flex justify-between items-center p-3 rounded-2xl bg-muted/40">
                              <span className="text-xs font-medium">LinkedIn Sourcing</span>
                              <span className="text-[10px] bg-emerald-500 text-white px-2 py-0.5 rounded-full font-bold">READY</span>
                           </div>
                           <div className="flex justify-between items-center p-3 rounded-2xl bg-muted/40">
                              <span className="text-xs font-medium">Email Enrichment</span>
                              <span className="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">STANDBY</span>
                           </div>
                           <div className="flex justify-between items-center p-3 rounded-2xl bg-muted/40 opacity-50">
                              <span className="text-xs font-medium">Direct Apply</span>
                              <span className="text-[10px] bg-muted-foreground text-white px-2 py-0.5 rounded-full font-bold">LOCKED</span>
                           </div>
                           <Button variant="outline" className="w-full rounded-xl border-dashed">Refresh API Stream</Button>
                        </div>
                     </div>
                  </div>
               </div>
            </motion.div>

            {/* Sidebar Stats Area */}
            <motion.div variants={item} className="md:col-span-4 space-y-6">
               <div className="card bg-background border rounded-[40px] p-8 shadow-sm flex flex-col items-center text-center">
                  <div className="w-32 h-32 rounded-full border-8 border-muted relative flex items-center justify-center mb-6">
                     <div className="absolute inset-0 border-8 border-primary rounded-full border-t-transparent animate-[spin_3s_linear_infinite]" />
                     <div className="text-center">
                        <p className="text-3xl font-black">{stats?.sent_today || 0}</p>
                        <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Sent</p>
                     </div>
                  </div>
                  <h3 className="text-lg font-extrabold mb-2 uppercase tracking-wide">Daily Quota</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed mb-6">You've reached <span className="text-primary font-bold">{((stats?.sent_today || 0) / 20 * 100).toFixed(0)}%</span> of your daily 20-message target.</p>
                  <Button className="w-full rounded-2xl h-12 shadow-lg shadow-primary/20">Boost outreach</Button>
               </div>

               <div className="card bg-background border rounded-[32px] p-6 shadow-sm">
                  <h3 className="font-bold mb-4">API Health</h3>
                  <div className="grid grid-cols-2 gap-3">
                     {stats?.api_health?.map((api: any, i: number) => (
                        <div key={i} className="flex items-center gap-2 p-2 rounded-xl bg-muted/20 border">
                           <div className={cn("w-2 h-2 rounded-full", api.status === 'healthy' ? "bg-emerald-500" : "bg-muted-foreground")} />
                           <span className="text-[10px] font-bold uppercase overflow-hidden truncate">{api.name}</span>
                        </div>
                     ))}
                  </div>
               </div>
            </motion.div>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
