# ─── Magneetar ProGuard Rules ─────────────────────────────────────────────────
# Keep app components (Activities, Services, Receivers)
-keep class com.magneetar.app.** { *; }

# ─── OkHttp ───────────────────────────────────────────────────────────────────
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }
-keepnames class okhttp3.internal.publicsuffix.PublicSuffixDatabase

# ─── Kotlin Coroutines ────────────────────────────────────────────────────────
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.coroutines.** {
    volatile <fields>;
}

# ─── Firebase / FCM ──────────────────────────────────────────────────────────
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.firebase.**
-dontwarn com.google.android.gms.**

# ─── WorkManager ──────────────────────────────────────────────────────────────
-keep class androidx.work.** { *; }
-dontwarn androidx.work.**

# ─── Sentry Crash Reporting ───────────────────────────────────────────────────
-keep class io.sentry.** { *; }
-dontwarn io.sentry.**
-keepattributes LineNumberTable,SourceFile

# ─── Gson / JSON ──────────────────────────────────────────────────────────────
-keep class org.json.** { *; }
-dontwarn org.json.**

# ─── Kotlin ───────────────────────────────────────────────────────────────────
-keep class kotlin.Metadata { *; }
-dontwarn kotlin.**

# ─── AndroidX ─────────────────────────────────────────────────────────────────
-keep class androidx.core.** { *; }
-keep class androidx.appcompat.** { *; }
-dontwarn androidx.**

# ─── Keep BuildConfig (SERVER_URL, API_KEY) ──────────────────────────────────
-keep class com.magneetar.app.BuildConfig { *; }

# ─── General Android ──────────────────────────────────────────────────────────
-keepattributes *Annotation*
-keepattributes SourceFile,LineNumberTable
-keepattributes EnclosingMethod
-keepattributes InnerClasses

# Keep serializable/parcelable classes
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    !static !transient <fields>;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}
-keepclassmembers class * implements android.os.Parcelable {
    public static final android.os.Parcelable$Creator CREATOR;
}
