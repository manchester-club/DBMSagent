void
RunObjectPostCreateHook(void)
{
	if (object_access_hook)
	{
		object_access_hook();
	}
}
