
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  
  "graphql_public": {
          Tables: {
            [_ in never]: never
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "graphql":
{ Args: { "extensions"?: Json,"operationName"?: string,"query"?: string,"variables"?: Json }; Returns: Json
                           }
          }
          Enums: {
            [_ in never]: never
          }
          CompositeTypes: {
            [_ in never]: never
          }
        },"public": {
          Tables: {
            "app_owner": {
                  Row: {
                    "created_at": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    
                  ]
                },"documents": {
                  Row: {
                    "content": NonNullable<Json>,"cost_usd": number | null,"created_at": string,"docx_path": string | null,"id": string,"job_id": string,"kind": string,"model": string | null,"pdf_path": string | null,"state": string,"template": string,"version": number
                  }
                  ComputedFields: never
                  Insert: {
                    "content": NonNullable<Json>,"cost_usd"?: number | null,"created_at"?: string,"docx_path"?: string | null,"id"?: string,"job_id": string,"kind": string,"model"?: string | null,"pdf_path"?: string | null,"state"?: string,"template": string,"version"?: number
                  }
                  Update: {
                    "content"?: NonNullable<Json>,"cost_usd"?: number | null,"created_at"?: string,"docx_path"?: string | null,"id"?: string,"job_id"?: string,"kind"?: string,"model"?: string | null,"pdf_path"?: string | null,"state"?: string,"template"?: string,"version"?: number
                  }
                  Relationships: [
                    {
      foreignKeyName: "documents_job_id_fkey"
      columns: ["job_id"]
isOneToOne: false
      referencedRelation: "jobs"
      referencedColumns: ["id"]
    }
                  ]
                },"jobs": {
                  Row: {
                    "applied_at": string | null,"closed_at": string | null,"company": string,"contacts": NonNullable<Json>,"created_at": string,"dedupe_key": string | null,"description": string | null,"employment_type": string | null,"filter_reason": string | null,"first_seen_at": string,"fit_reason": string | null,"fit_score": number | null,"id": string,"last_seen_at": string,"location": string | null,"notes": string,"pipeline_state": Database["public"]['Enums']["pipeline_state"],"posted_at": string | null,"remote_type": string | null,"salary_max": number | null,"salary_min": number | null,"source": Database["public"]['Enums']["job_source"],"source_board": string | null,"source_job_id": string | null,"start_from": string | null,"start_kind": string | null,"start_note": string | null,"start_to": string | null,"status": Database["public"]['Enums']["application_status"],"tags": (string)[],"term_end": string | null,"title": string,"track": Database["public"]['Enums']["job_track"] | null,"updated_at": string,"url": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "applied_at"?: string | null,"closed_at"?: string | null,"company": string,"contacts"?: NonNullable<Json>,"created_at"?: string,"dedupe_key"?: string | null,"description"?: string | null,"employment_type"?: string | null,"filter_reason"?: string | null,"first_seen_at"?: string,"fit_reason"?: string | null,"fit_score"?: number | null,"id"?: string,"last_seen_at"?: string,"location"?: string | null,"notes"?: string,"pipeline_state"?: Database["public"]['Enums']["pipeline_state"],"posted_at"?: string | null,"remote_type"?: string | null,"salary_max"?: number | null,"salary_min"?: number | null,"source"?: Database["public"]['Enums']["job_source"],"source_board"?: string | null,"source_job_id"?: string | null,"start_from"?: string | null,"start_kind"?: string | null,"start_note"?: string | null,"start_to"?: string | null,"status"?: Database["public"]['Enums']["application_status"],"tags"?: (string)[],"term_end"?: string | null,"title": string,"track"?: Database["public"]['Enums']["job_track"] | null,"updated_at"?: string,"url"?: string | null
                  }
                  Update: {
                    "applied_at"?: string | null,"closed_at"?: string | null,"company"?: string,"contacts"?: NonNullable<Json>,"created_at"?: string,"dedupe_key"?: string | null,"description"?: string | null,"employment_type"?: string | null,"filter_reason"?: string | null,"first_seen_at"?: string,"fit_reason"?: string | null,"fit_score"?: number | null,"id"?: string,"last_seen_at"?: string,"location"?: string | null,"notes"?: string,"pipeline_state"?: Database["public"]['Enums']["pipeline_state"],"posted_at"?: string | null,"remote_type"?: string | null,"salary_max"?: number | null,"salary_min"?: number | null,"source"?: Database["public"]['Enums']["job_source"],"source_board"?: string | null,"source_job_id"?: string | null,"start_from"?: string | null,"start_kind"?: string | null,"start_note"?: string | null,"start_to"?: string | null,"status"?: Database["public"]['Enums']["application_status"],"tags"?: (string)[],"term_end"?: string | null,"title"?: string,"track"?: Database["public"]['Enums']["job_track"] | null,"updated_at"?: string,"url"?: string | null
                  }
                  Relationships: [
                    
                  ]
                },"profile_versions": {
                  Row: {
                    "created_at": string,"data": NonNullable<Json>,"note": string,"version": number
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"data": NonNullable<Json>,"note"?: string,"version"?: never
                  }
                  Update: {
                    "created_at"?: string,"data"?: NonNullable<Json>,"note"?: string,"version"?: never
                  }
                  Relationships: [
                    
                  ]
                },"runs": {
                  Row: {
                    "cost_usd": number,"counts": NonNullable<Json>,"error": string | null,"finished_at": string | null,"id": string,"kind": string,"started_at": string,"status": string
                  }
                  ComputedFields: never
                  Insert: {
                    "cost_usd"?: number,"counts"?: NonNullable<Json>,"error"?: string | null,"finished_at"?: string | null,"id"?: string,"kind": string,"started_at"?: string,"status"?: string
                  }
                  Update: {
                    "cost_usd"?: number,"counts"?: NonNullable<Json>,"error"?: string | null,"finished_at"?: string | null,"id"?: string,"kind"?: string,"started_at"?: string,"status"?: string
                  }
                  Relationships: [
                    
                  ]
                },"scores": {
                  Row: {
                    "cost_usd": number | null,"created_at": string,"details": NonNullable<Json>,"id": number,"input_tokens": number | null,"job_id": string,"model": string,"output_tokens": number | null,"reason": string,"score": number,"track": Database["public"]['Enums']["job_track"] | null
                  }
                  ComputedFields: never
                  Insert: {
                    "cost_usd"?: number | null,"created_at"?: string,"details"?: NonNullable<Json>,"id"?: never,"input_tokens"?: number | null,"job_id": string,"model": string,"output_tokens"?: number | null,"reason": string,"score": number,"track"?: Database["public"]['Enums']["job_track"] | null
                  }
                  Update: {
                    "cost_usd"?: number | null,"created_at"?: string,"details"?: NonNullable<Json>,"id"?: never,"input_tokens"?: number | null,"job_id"?: string,"model"?: string,"output_tokens"?: number | null,"reason"?: string,"score"?: number,"track"?: Database["public"]['Enums']["job_track"] | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "scores_job_id_fkey"
      columns: ["job_id"]
isOneToOne: false
      referencedRelation: "jobs"
      referencedColumns: ["id"]
    }
                  ]
                },"settings": {
                  Row: {
                    "data": NonNullable<Json>,"id": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "data"?: NonNullable<Json>,"id"?: number,"updated_at"?: string
                  }
                  Update: {
                    "data"?: NonNullable<Json>,"id"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    
                  ]
                },"status_history": {
                  Row: {
                    "changed_at": string,"from_status": Database["public"]['Enums']["application_status"] | null,"id": number,"job_id": string,"to_status": Database["public"]['Enums']["application_status"]
                  }
                  ComputedFields: never
                  Insert: {
                    "changed_at"?: string,"from_status"?: Database["public"]['Enums']["application_status"] | null,"id"?: never,"job_id": string,"to_status": Database["public"]['Enums']["application_status"]
                  }
                  Update: {
                    "changed_at"?: string,"from_status"?: Database["public"]['Enums']["application_status"] | null,"id"?: never,"job_id"?: string,"to_status"?: Database["public"]['Enums']["application_status"]
                  }
                  Relationships: [
                    {
      foreignKeyName: "status_history_job_id_fkey"
      columns: ["job_id"]
isOneToOne: false
      referencedRelation: "jobs"
      referencedColumns: ["id"]
    }
                  ]
                },"suggestions": {
                  Row: {
                    "created_at": string,"decided_at": string | null,"decision": string,"document_id": string,"final_text": string | null,"id": string,"original_text": string | null,"path": string,"rationale": string,"suggested_text": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"decided_at"?: string | null,"decision"?: string,"document_id": string,"final_text"?: string | null,"id"?: string,"original_text"?: string | null,"path": string,"rationale": string,"suggested_text": string
                  }
                  Update: {
                    "created_at"?: string,"decided_at"?: string | null,"decision"?: string,"document_id"?: string,"final_text"?: string | null,"id"?: string,"original_text"?: string | null,"path"?: string,"rationale"?: string,"suggested_text"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "suggestions_document_id_fkey"
      columns: ["document_id"]
isOneToOne: false
      referencedRelation: "documents"
      referencedColumns: ["id"]
    }
                  ]
                },"tasks": {
                  Row: {
                    "created_at": string,"error": string | null,"id": string,"input": NonNullable<Json>,"job_id": string | null,"kind": string,"result": Json | null,"step": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"error"?: string | null,"id"?: string,"input"?: NonNullable<Json>,"job_id"?: string | null,"kind": string,"result"?: Json | null,"step"?: string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"error"?: string | null,"id"?: string,"input"?: NonNullable<Json>,"job_id"?: string | null,"kind"?: string,"result"?: Json | null,"step"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "tasks_job_id_fkey"
      columns: ["job_id"]
isOneToOne: false
      referencedRelation: "jobs"
      referencedColumns: ["id"]
    }
                  ]
                }
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "close_missing_postings":
{ Args: { "board": string,"seen_ids": (string)[] }; Returns: number
                           },
"ingest_postings":
{ Args: { "postings": Json }; Returns: Json
                           },
"is_owner":
{ Args: Record<PropertyKey, never>; Returns: boolean
                           },
"record_scores":
{ Args: { "scores": Json }; Returns: number
                           },
"record_timing":
{ Args: { "timings": Json }; Returns: number
                           },
"save_tailored":
{ Args: { "job": string,"payload": Json }; Returns: Json
                           }
          }
          Enums: {
            "application_status": "new"|"docs_ready"|"applied"|"interviewing"|"offer"|"rejected"|"withdrawn"|"not_interested","job_source": "manual"|"greenhouse"|"lever"|"ashby"|"workday"|"adzuna"|"jsearch"|"higheredjobs"|"other"|"smartrecruiters"|"jibe"|"silkroad"|"pageup"|"peopleclick"|"avature","job_track": "software"|"program_admin"|"hybrid"|"research","pipeline_state": "new"|"filtered_out"|"scored"|"below_threshold"|"tailoring"|"needs_approval"|"ready"|"error"
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "graphql_public": {
          Enums: {
            
          }
        },"public": {
          Enums: {
            "application_status": ["new", "docs_ready", "applied", "interviewing", "offer", "rejected", "withdrawn", "not_interested"],"job_source": ["manual", "greenhouse", "lever", "ashby", "workday", "adzuna", "jsearch", "higheredjobs", "other", "smartrecruiters", "jibe", "silkroad", "pageup", "peopleclick", "avature"],"job_track": ["software", "program_admin", "hybrid", "research"],"pipeline_state": ["new", "filtered_out", "scored", "below_threshold", "tailoring", "needs_approval", "ready", "error"]
          }
        }
} as const
