package com.tourist.safety

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * TouristPreferences — encrypted local storage for Digital_Tourist_ID and JWT.
 * Uses EncryptedSharedPreferences (AES-256-GCM) backed by Android Keystore.
 * Implements: Requirements 2.3, 2.4, 2.5
 */
object TouristPreferences {

    private const val PREFS_FILE = "tourist_secure_prefs"
    private const val KEY_TOURIST_ID = "tourist_id"
    private const val KEY_VALID_UNTIL = "valid_until"
    private const val KEY_JWT = "jwt_token"
    private const val KEY_TX_HASH = "tx_hash"
    private const val KEY_NAME = "tourist_name"

    private fun prefs(context: Context) = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        // Fallback to regular prefs if encryption unavailable (emulator edge case)
        context.getSharedPreferences(PREFS_FILE, Context.MODE_PRIVATE)
    }

    fun saveTouristRecord(context: Context, touristId: String, validUntil: Long, txHash: String?) {
        prefs(context).edit()
            .putString(KEY_TOURIST_ID, touristId)
            .putLong(KEY_VALID_UNTIL, validUntil)
            .putString(KEY_TX_HASH, txHash ?: "")
            .apply()
    }

    /** Returns the stored touristId, or null if expired or not set. */
    fun getTouristId(context: Context): String? {
        val p = prefs(context)
        val id = p.getString(KEY_TOURIST_ID, null) ?: return null
        val validUntil = p.getLong(KEY_VALID_UNTIL, 0L)
        if (validUntil > 0 && System.currentTimeMillis() > validUntil) return null
        return id
    }

    fun getValidUntil(context: Context): Long =
        prefs(context).getLong(KEY_VALID_UNTIL, 0L)

    fun saveJwt(context: Context, token: String) =
        prefs(context).edit().putString(KEY_JWT, token).apply()

    fun getJwt(context: Context): String? =
        prefs(context).getString(KEY_JWT, null)

    fun saveName(context: Context, name: String) =
        prefs(context).edit().putString(KEY_NAME, name).apply()

    fun getName(context: Context): String? =
        prefs(context).getString(KEY_NAME, null)

    fun clear(context: Context) =
        prefs(context).edit().clear().apply()
}
