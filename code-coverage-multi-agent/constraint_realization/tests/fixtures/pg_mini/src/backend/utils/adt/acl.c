void
ExecGrantStmt(void)
{
	if (aclmask)
	{
		elog(ERROR, "permission denied");
	}
}
